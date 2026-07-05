"""End-to-end: SDK → real local TrailMark API → verify via the entries API.

Skipped automatically when the local stack isn't running
(docker compose -f infrastructure/docker-compose.yml up -d + uvicorn on :8000).
"""

import uuid

import httpx
import pytest

from trailmark import TrailMarkClient, TrailMarkConfig, audit, set_default_client

API = "http://localhost:8000"


def api_available() -> bool:
    try:
        return httpx.get(f"{API}/health", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not api_available(), reason="local TrailMark API not running")


def test_sdk_to_live_ledger_roundtrip(tmp_path):
    firm = f"firm_sdk_e2e_{uuid.uuid4().hex[:8]}"
    client = TrailMarkClient(
        TrailMarkConfig(
            api_key=f"tmk_dev_{firm}",
            firm_id=firm,
            api_url=API,
            agent_id="agent_sdk_test",
            framework="pytest",
            spool_dir=tmp_path / "spool",
        )
    )
    set_default_client(client)
    try:
        @audit(action_name="wire_transfer_review")
        def review_wire(amount: int):
            return {"decision": "flagged for review"}

        review_wire(amount=500_000)
        assert client.flush(10.0), "event was not delivered to the live API"

        headers = {"Authorization": f"Bearer tmk_dev_{firm}"}
        entries = httpx.get(f"{API}/v1/entries", headers=headers).json()
        assert entries["total"] == 1
        assert entries["chain_integrity_verified"] is True

        entry = entries["entries"][0]
        assert entry["action_name"] == "wire_transfer_review"
        assert entry["requires_attestation"] is True  # heuristics: wire + 500k
        assert entry["status"] == "PENDING_REVIEW"

        # The full WORM record contains the SDK-captured arguments
        full = httpx.get(f"{API}/v1/entries/{entry['ledger_id']}", headers=headers).json()
        assert full["input"]["arguments"] == {"amount": 500000}
        assert full["agent"]["agent_id"] == "agent_sdk_test"

        # spool must be empty — nothing was lost or left behind
        assert list((tmp_path / "spool").glob("*.json")) == []
    finally:
        set_default_client(None)
        client._stop.set()
