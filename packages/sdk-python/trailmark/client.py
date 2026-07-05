"""TrailMark client: configuration, event assembly, and background delivery.

Delivery guarantees:

* **Never slow the agent.** ``submit()`` is a lock-free queue put — no network
  I/O ever happens on the caller's thread or event loop.
* **Never lose an event.** A background worker delivers with retries and
  exponential backoff; events that cannot be delivered (network down, process
  exiting, queue overflow) are spooled to disk as JSON and replayed on the
  next client start. Permanently rejected events (4xx) are quarantined to a
  ``rejected/`` directory for operator review rather than silently dropped.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .risk import RiskConfig

logger = logging.getLogger("trailmark")

_UNSET_HASH = "sha256:" + "0" * 64


@dataclass
class TrailMarkConfig:
    api_key: str
    firm_id: str
    api_url: str = "https://api.trailmark.ai"
    # Default agent identity; individual traces may override
    agent_id: str = "unnamed_agent"
    framework: str = "custom"
    agent_version: str | None = None
    registered_rep_id: str | None = None
    # Policy in effect — set these from your policy registry
    policy_version_id: str = "unversioned"
    policy_version_hash: str = _UNSET_HASH
    regulatory_tags: list[str] = field(default_factory=lambda: ["SEC_17a4", "FINRA_3110"])
    risk: RiskConfig = field(default_factory=RiskConfig)
    # Delivery tuning
    spool_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("TRAILMARK_SPOOL_DIR", Path.home() / ".trailmark" / "spool")
        )
    )
    max_queue_size: int = 10_000
    request_timeout: float = 10.0
    max_retries: int = 3
    backoff_base: float = 0.5


def _jsonable(value: Any, depth: int = 0) -> Any:
    """Best-effort conversion to JSON-serializable structures. Falls back to
    repr() — an imperfect record beats a lost one."""
    if depth > 6:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, depth + 1) for v in value]
    if hasattr(value, "model_dump"):  # pydantic v2
        try:
            return _jsonable(value.model_dump(), depth + 1)
        except Exception:  # noqa: BLE001 — auditing must not raise
            return repr(value)
    return repr(value)


class TrailMarkClient:
    def __init__(self, config: TrailMarkConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._transport = transport  # test seam
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=config.max_queue_size)
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.default_session_id = f"sess_{uuid.uuid4().hex[:12]}"
        config.spool_dir.mkdir(parents=True, exist_ok=True)
        atexit.register(self.close)

    # ---------------------------------------------------------------- submit

    def submit(self, event: dict) -> None:
        """Enqueue an event for background delivery. Non-blocking, never raises."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._spool(event)  # overflow → disk, not the floor
        self._ensure_worker()

    def build_event(
        self,
        *,
        action_type: str,
        action_name: str,
        input_payload: Any,
        output_payload: Any,
        reasoning_trace: str | None,
        risk: dict,
        session_id: str | None = None,
        registered_rep_id: str | None = None,
        agent_id: str | None = None,
        framework: str | None = None,
    ) -> dict:
        c = self.config
        return {
            "firm_id": c.firm_id,
            "agent": {
                "agent_id": agent_id or c.agent_id,
                "framework": framework or c.framework,
                "agent_version": c.agent_version,
            },
            "session": {
                "session_id": session_id or self.default_session_id,
                "registered_rep_id": registered_rep_id or c.registered_rep_id,
            },
            "action": {"action_type": action_type, "action_name": action_name},
            "policy": {
                "policy_version_id": c.policy_version_id,
                "policy_version_hash": c.policy_version_hash,
            },
            "risk": risk,
            "input": _jsonable(input_payload),
            "output": _jsonable(output_payload),
            "reasoning_trace": reasoning_trace,
            "regulatory_tags": list(c.regulatory_tags),
        }

    # ------------------------------------------------------------- lifecycle

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until the queue drains (best effort). Returns True if fully
        drained within the timeout."""
        self._ensure_worker()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.empty() and not self._delivering:
                return True
            time.sleep(0.02)
        return False

    def close(self, timeout: float = 5.0) -> None:
        """Drain what we can, spool the rest. Registered via atexit."""
        if self._worker is not None and self._worker.is_alive():
            self.flush(timeout)
            self._stop.set()
            self._worker.join(timeout=2.0)
        # Anything still queued goes to disk — never lost.
        while True:
            try:
                self._spool(self._queue.get_nowait())
            except queue.Empty:
                break

    # ---------------------------------------------------------------- worker

    _delivering: bool = False

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._stop.clear()
                self._worker = threading.Thread(
                    target=self._run, name="trailmark-delivery", daemon=True
                )
                self._worker.start()

    def _run(self) -> None:
        with httpx.Client(
            timeout=self.config.request_timeout, transport=self._transport
        ) as http:
            self._replay_spool(http)
            while not self._stop.is_set():
                try:
                    event = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._delivering = True
                try:
                    self._deliver(http, event)
                finally:
                    self._delivering = False
                    self._queue.task_done()

    def _deliver(self, http: httpx.Client, event: dict) -> None:
        for attempt in range(self.config.max_retries):
            try:
                resp = http.post(
                    f"{self.config.api_url}/v1/ingest",
                    json=event,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
            except httpx.HTTPError as exc:
                logger.warning("TrailMark delivery attempt %d failed: %s", attempt + 1, exc)
            else:
                if resp.status_code < 300:
                    return
                if 400 <= resp.status_code < 500:
                    # Will never succeed as-is — quarantine for operator review.
                    logger.error(
                        "TrailMark event rejected (%d): %s", resp.status_code, resp.text[:200]
                    )
                    self._spool(event, subdir="rejected")
                    return
                logger.warning(
                    "TrailMark delivery attempt %d got %d", attempt + 1, resp.status_code
                )
            time.sleep(self.config.backoff_base * (2**attempt))
        self._spool(event)

    # ----------------------------------------------------------------- spool

    def _spool(self, event: dict, subdir: str = "") -> None:
        try:
            target = self.config.spool_dir / subdir if subdir else self.config.spool_dir
            target.mkdir(parents=True, exist_ok=True)
            name = f"{time.time_ns()}_{uuid.uuid4().hex[:8]}.json"
            (target / name).write_text(json.dumps(event, default=repr))
        except OSError as exc:  # last resort: log loudly rather than crash the agent
            logger.error("TrailMark could not spool event to disk: %s", exc)

    def _replay_spool(self, http: httpx.Client) -> None:
        try:
            spooled = sorted(self.config.spool_dir.glob("*.json"))
        except OSError:
            return
        for path in spooled:
            try:
                event = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            resp = None
            try:
                resp = http.post(
                    f"{self.config.api_url}/v1/ingest",
                    json=event,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
            except httpx.HTTPError:
                return  # network still down; keep the spool intact
            if resp.status_code < 300:
                path.unlink(missing_ok=True)
            elif 400 <= resp.status_code < 500:
                self._spool(event, subdir="rejected")
                path.unlink(missing_ok=True)
