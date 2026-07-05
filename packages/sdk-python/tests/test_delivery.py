"""Delivery guarantees: non-blocking submit, spool fallback, never lose an event."""

import json
import time

import httpx

from trailmark import TrailMarkClient

from .conftest import make_config


def make_event(client: TrailMarkClient, name: str = "test_action") -> dict:
    return client.build_event(
        action_type="tool_call",
        action_name=name,
        input_payload={"n": 1},
        output_payload={"ok": True},
        reasoning_trace=None,
        risk={"risk_score": 0.1, "risk_tier": "LOW", "risk_flags": [],
              "requires_supervisor_review": False},
    )


def test_submit_never_blocks_on_slow_api(tmp_path):
    def slow_handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.5)  # a struggling API
        return httpx.Response(201, json={})

    client = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(slow_handler))
    started = time.monotonic()
    for _ in range(20):
        client.submit(make_event(client))
    elapsed = time.monotonic() - started
    assert elapsed < 0.1, f"submit blocked the caller for {elapsed:.3f}s"
    client._stop.set()


def test_failed_delivery_spools_to_disk(tmp_path):
    def down_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    client = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(down_handler))
    client.submit(make_event(client, "spooled_action"))
    client.flush(timeout=5.0)
    client._stop.set()

    spooled = list((tmp_path / "spool").glob("*.json"))
    assert len(spooled) == 1
    assert json.loads(spooled[0].read_text())["action"]["action_name"] == "spooled_action"


def test_spool_replays_when_api_recovers(tmp_path):
    # First client: API down → event lands on disk.
    def down(request):
        raise httpx.ConnectError("network down")

    c1 = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(down))
    c1.submit(make_event(c1, "survives_restart"))
    c1.flush(timeout=5.0)
    c1._stop.set()
    assert len(list((tmp_path / "spool").glob("*.json"))) == 1

    # Second client (simulated process restart): API is back → spool replays.
    received = []

    def up(request):
        received.append(json.loads(request.content))
        return httpx.Response(201, json={})

    c2 = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(up))
    c2.submit(make_event(c2, "fresh_event"))  # starts the worker
    assert c2.flush(timeout=5.0)
    c2._stop.set()

    names = {e["action"]["action_name"] for e in received}
    assert names == {"survives_restart", "fresh_event"}
    assert list((tmp_path / "spool").glob("*.json")) == []  # spool drained


def test_rejected_events_are_quarantined_not_lost(tmp_path):
    def reject(request):
        return httpx.Response(422, json={"error": {"code": "validation_error"}})

    client = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(reject))
    client.submit(make_event(client, "malformed"))
    client.flush(timeout=5.0)
    client._stop.set()

    rejected = list((tmp_path / "spool" / "rejected").glob("*.json"))
    assert len(rejected) == 1
    assert list((tmp_path / "spool").glob("*.json")) == []  # not retried forever


def test_server_errors_retry_then_spool(tmp_path):
    attempts = []

    def flaky(request):
        attempts.append(1)
        return httpx.Response(503)

    config = make_config(tmp_path, max_retries=3)
    client = TrailMarkClient(config, transport=httpx.MockTransport(flaky))
    client.submit(make_event(client))
    client.flush(timeout=5.0)
    client._stop.set()

    assert len(attempts) == 3  # retried
    assert len(list((tmp_path / "spool").glob("*.json"))) == 1  # then preserved


def test_close_spools_undelivered_queue(tmp_path):
    def slow(request):
        time.sleep(2.0)
        return httpx.Response(201, json={})

    client = TrailMarkClient(make_config(tmp_path), transport=httpx.MockTransport(slow))
    for i in range(5):
        client.submit(make_event(client, f"pending_{i}"))
    client.close(timeout=0.2)  # process exiting NOW

    # in flight + spooled must account for everything not delivered
    spooled = list((tmp_path / "spool").glob("*.json"))
    assert len(spooled) >= 3  # the queue remainder hit disk
