"""Tracing primitives: the @audit decorator and the trace() context manager.

Both build one immutable ledger event per traced action. Exceptions inside a
traced block are themselves audited (flagged ``exception_raised``) and then
re-raised — a failed agent action is precisely the kind of record a
supervisor needs to see.
"""

from __future__ import annotations

import contextvars
import functools
import inspect
import time
import traceback
import uuid
from contextlib import contextmanager
from typing import Any, Callable

from . import risk as risk_module
from .client import TrailMarkClient, _jsonable

_current_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trailmark_session", default=None
)
_current_rep: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trailmark_rep", default=None
)

# The module-level client configured via trailmark.configure()
_default_client: TrailMarkClient | None = None


def set_default_client(client: TrailMarkClient | None) -> None:
    global _default_client
    _default_client = client


def get_default_client() -> TrailMarkClient:
    if _default_client is None:
        raise RuntimeError(
            "TrailMark is not configured. Call trailmark.configure(api_key=..., "
            "firm_id=...) once at startup, or pass client= explicitly."
        )
    return _default_client


@contextmanager
def session(session_id: str | None = None, registered_rep_id: str | None = None):
    """Scope traced actions to a session/registered rep (contextvar-based, so
    it composes with asyncio and threads)."""
    sid_token = _current_session.set(session_id or f"sess_{uuid.uuid4().hex[:12]}")
    rep_token = _current_rep.set(registered_rep_id)
    try:
        yield
    finally:
        _current_session.reset(sid_token)
        _current_rep.reset(rep_token)


class Trace:
    """Mutable capture surface for one agent action; submits on exit."""

    def __init__(
        self,
        action_name: str,
        *,
        action_type: str = "tool_call",
        client: TrailMarkClient | None = None,
        agent_id: str | None = None,
        framework: str | None = None,
    ):
        self._client = client or get_default_client()
        self.action_name = action_name
        self.action_type = action_type
        self.agent_id = agent_id
        self.framework = framework
        self.input: Any = {}
        self.output: Any = {}
        self.reasoning: str | None = None
        self._risk_override: dict | None = None
        self._extra_flags: list[str] = []
        self._submitted = False

    # ------------------------------------------------------------- capture

    def set_input(self, payload: Any) -> None:
        self.input = payload

    def set_output(self, payload: Any) -> None:
        self.output = payload

    def set_reasoning(self, text: str) -> None:
        self.reasoning = text

    def add_risk_flag(self, flag: str) -> None:
        self._extra_flags.append(flag)

    def set_risk(
        self,
        *,
        risk_score: float,
        risk_tier: str | None = None,
        risk_flags: list[str] | None = None,
        requires_supervisor_review: bool | None = None,
    ) -> None:
        """Explicit risk override — heuristics are skipped entirely."""
        config = self._client.config.risk
        self._risk_override = {
            "risk_score": risk_score,
            "risk_tier": risk_tier or risk_module.tier_for(risk_score, config),
            "risk_flags": risk_flags or [],
            "requires_supervisor_review": (
                requires_supervisor_review
                if requires_supervisor_review is not None
                else risk_score >= config.review_threshold
            ),
        }

    # -------------------------------------------------------------- submit

    def _finish(self, exc: BaseException | None = None) -> None:
        if self._submitted:
            return
        self._submitted = True

        if exc is not None:
            self.add_risk_flag("exception_raised")
            self.output = {
                "error": repr(exc),
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )[-2000:],
                "partial_output": _jsonable(self.output),
            }

        if self._risk_override is not None:
            risk = dict(self._risk_override)
            risk["risk_flags"] = list(dict.fromkeys(risk["risk_flags"] + self._extra_flags))
        else:
            assessment = risk_module.assess(
                self.action_type,
                self.action_name,
                _jsonable(self.input),
                self._client.config.risk,
            )
            risk = assessment.model_dump()
            risk["risk_flags"] = list(dict.fromkeys(risk["risk_flags"] + self._extra_flags))

        event = self._client.build_event(
            action_type=self.action_type,
            action_name=self.action_name,
            input_payload=self.input,
            output_payload=self.output,
            reasoning_trace=self.reasoning,
            risk=risk,
            session_id=_current_session.get(),
            registered_rep_id=_current_rep.get(),
            agent_id=self.agent_id,
            framework=self.framework,
        )
        self._client.submit(event)

    # ------------------------------------------------- sync + async context

    def __enter__(self) -> "Trace":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._finish(exc)

    async def __aenter__(self) -> "Trace":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._finish(exc)


def trace(
    action_name: str,
    *,
    action_type: str = "tool_call",
    client: TrailMarkClient | None = None,
    agent_id: str | None = None,
    framework: str | None = None,
) -> Trace:
    """``with trailmark.trace("...") as t:`` or ``async with`` — both work."""
    return Trace(
        action_name,
        action_type=action_type,
        client=client,
        agent_id=agent_id,
        framework=framework,
    )


def audit(
    action_name: str | None = None,
    *,
    action_type: str = "function_call",
    capture_args: bool = True,
    snapshot_before: Callable[[], Any] | None = None,
    snapshot_after: Callable[[], Any] | None = None,
    client: TrailMarkClient | None = None,
    agent_id: str | None = None,
    framework: str | None = None,
):
    """Decorator form. Works on sync and async functions.

    ``snapshot_before``/``snapshot_after`` are user-supplied zero-arg callables
    whose return values are recorded as pre/post state alongside the call
    arguments and return value.
    """

    def decorate(fn: Callable) -> Callable:
        name = action_name or fn.__name__

        def build_input(args: tuple, kwargs: dict) -> dict:
            payload: dict[str, Any] = {}
            if capture_args:
                try:
                    bound = inspect.signature(fn).bind_partial(*args, **kwargs)
                    payload["arguments"] = {
                        k: _jsonable(v) for k, v in bound.arguments.items() if k != "self"
                    }
                except TypeError:
                    payload["arguments"] = {
                        "args": _jsonable(args),
                        "kwargs": _jsonable(kwargs),
                    }
            if snapshot_before is not None:
                payload["state_before"] = _jsonable(snapshot_before())
            return payload

        def build_output(result: Any, started: float) -> dict:
            payload: dict[str, Any] = {
                "result": _jsonable(result),
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
            if snapshot_after is not None:
                payload["state_after"] = _jsonable(snapshot_after())
            return payload

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t = Trace(
                    name,
                    action_type=action_type,
                    client=client,
                    agent_id=agent_id,
                    framework=framework,
                )
                t.set_input(build_input(args, kwargs))
                started = time.monotonic()
                async with t:
                    result = await fn(*args, **kwargs)
                    t.set_output(build_output(result, started))
                    return result

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            t = Trace(
                name,
                action_type=action_type,
                client=client,
                agent_id=agent_id,
                framework=framework,
            )
            t.set_input(build_input(args, kwargs))
            started = time.monotonic()
            with t:
                result = fn(*args, **kwargs)
                t.set_output(build_output(result, started))
                return result

        return sync_wrapper

    return decorate
