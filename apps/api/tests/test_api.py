"""Phase 2 API integration tests — full HTTP round-trips over the ASGI app.

Auth uses dev tokens (tmk_dev_<firm_id>); Clerk JWT mode is exercised in
production deployments where CLERK_JWKS_URL is set.
"""

import httpx
import pytest

from db.connection import close_pool
from main import app
from tests.test_ledger import make_event

FIRM_A = "firm_acme"
FIRM_B = "firm_other"
AUTH_A = {"Authorization": "Bearer tmk_dev_" + FIRM_A}
AUTH_B = {"Authorization": "Bearer tmk_dev_" + FIRM_B}


@pytest.fixture
async def client(pool, worm_bucket):
    """HTTP client against the app. Depends on `pool` so each test gets a fresh
    schema; the app's own global pool is torn down afterwards."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await close_pool()


def event_body(firm_id: str = FIRM_A, i: int = 0, **risk_kwargs) -> dict:
    return make_event(firm_id=firm_id, i=i, **risk_kwargs).model_dump(mode="json")


async def ingest_one(client, firm_id: str = FIRM_A, i: int = 0, **risk_kwargs) -> dict:
    headers = {"Authorization": f"Bearer tmk_dev_{firm_id}"}
    resp = await client.post("/v1/ingest", json=event_body(firm_id, i, **risk_kwargs), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------- auth

async def test_requests_without_token_are_401(client):
    for call in (
        client.post("/v1/ingest", json=event_body()),
        client.get("/v1/entries"),
        client.get("/v1/entries/entry_X"),
        client.get("/v1/chain/verify"),
    ):
        resp = await call
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "missing_token"


async def test_unrecognized_token_is_401(client):
    resp = await client.get("/v1/entries", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


async def test_ingest_firm_mismatch_is_403(client):
    resp = await client.post("/v1/ingest", json=event_body(FIRM_A), headers=AUTH_B)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "firm_mismatch"


# ---------------------------------------------------------------- ingest

async def test_ingest_returns_ledger_id_and_entry_hash(client, pool):
    body = await ingest_one(client)
    assert body["ledger_id"].startswith("entry_")
    assert body["entry_hash"].startswith("sha256:")
    assert body["sequence_number"] == 1
    row = await pool.fetchrow("SELECT firm_id FROM audit_entries WHERE ledger_id = $1", body["ledger_id"])
    assert row["firm_id"] == FIRM_A


async def test_ingest_invalid_payload_is_structured_422(client):
    bad = event_body()
    del bad["policy"]
    bad["unexpected_field"] = True
    resp = await client.post("/v1/ingest", json=bad, headers=AUTH_A)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    locs = {".".join(d["loc"]) for d in err["details"]}
    assert any("policy" in loc for loc in locs)
    assert any("unexpected_field" in loc for loc in locs)


# ---------------------------------------------------------------- entries list

async def test_list_entries_pagination_and_chain_flag(client):
    for i in range(5):
        await ingest_one(client, i=i)
    resp = await client.get("/v1/entries", params={"limit": 2, "offset": 0}, headers=AUTH_A)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["entries"]) == 2
    assert body["chain_integrity_verified"] is True
    # newest first
    assert body["entries"][0]["sequence_number"] > body["entries"][1]["sequence_number"]

    resp2 = await client.get("/v1/entries", params={"limit": 2, "offset": 4}, headers=AUTH_A)
    assert len(resp2.json()["entries"]) == 1


async def test_list_entries_filters(client):
    await ingest_one(client, i=1)
    await ingest_one(
        client, i=2,
        risk_score=0.95, risk_tier="CRITICAL",
        risk_flags=["large_notional"], requires_supervisor_review=True,
    )

    resp = await client.get("/v1/entries", params={"risk_tier": "CRITICAL"}, headers=AUTH_A)
    assert [e["risk_tier"] for e in resp.json()["entries"]] == ["CRITICAL"]

    resp = await client.get("/v1/entries", params={"requires_attestation": "true"}, headers=AUTH_A)
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["status"] == "PENDING_REVIEW"

    resp = await client.get("/v1/entries", params={"action_name": "rebalance"}, headers=AUTH_A)
    assert resp.json()["total"] == 2
    resp = await client.get("/v1/entries", params={"action_name": "no_such_action"}, headers=AUTH_A)
    assert resp.json()["total"] == 0

    resp = await client.get("/v1/entries", params={"agent_id": "agent_rebalancer"}, headers=AUTH_A)
    assert resp.json()["total"] == 2

    resp = await client.get(
        "/v1/entries", params={"date_from": "2099-01-01T00:00:00Z"}, headers=AUTH_A
    )
    assert resp.json()["total"] == 0


async def test_list_entries_is_firm_scoped(client):
    await ingest_one(client, firm_id=FIRM_A, i=1)
    await ingest_one(client, firm_id=FIRM_B, i=1)

    body_a = (await client.get("/v1/entries", headers=AUTH_A)).json()
    assert body_a["total"] == 1
    body_b = (await client.get("/v1/entries", headers=AUTH_B)).json()
    assert body_b["total"] == 1
    assert body_a["entries"][0]["ledger_id"] != body_b["entries"][0]["ledger_id"]


async def test_auto_approved_status_for_low_risk(client):
    await ingest_one(client, i=1)
    body = (await client.get("/v1/entries", headers=AUTH_A)).json()
    assert body["entries"][0]["status"] == "AUTO_APPROVED"


async def test_limit_above_100_is_rejected(client):
    resp = await client.get("/v1/entries", params={"limit": 101}, headers=AUTH_A)
    assert resp.status_code == 422


# ---------------------------------------------------------------- entry detail

async def test_get_entry_returns_full_worm_record(client):
    created = await ingest_one(client)
    resp = await client.get(f"/v1/entries/{created['ledger_id']}", headers=AUTH_A)
    assert resp.status_code == 200
    entry = resp.json()
    assert entry["@type"] == "AgentAuditEntry"
    assert entry["entry_hash"] == created["entry_hash"]
    assert entry["input"]["portfolio_id"] == "pf_0"
    assert entry["worm_object_lock_mode"] == "COMPLIANCE"


async def test_get_entry_cross_firm_is_404(client):
    created = await ingest_one(client, firm_id=FIRM_A)
    resp = await client.get(f"/v1/entries/{created['ledger_id']}", headers=AUTH_B)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- chain

async def test_chain_verify_endpoint(client):
    for i in range(3):
        await ingest_one(client, i=i)
    resp = await client.get("/v1/chain/verify", headers=AUTH_A)
    assert resp.status_code == 200
    assert resp.json() == {
        "firm_id": FIRM_A,
        "verified": True,
        "entries_checked": 3,
        "broken_at_sequence": None,
    }


async def test_chain_verify_reports_tampering_over_http(client, pool):
    entries = [await ingest_one(client, i=i) for i in range(3)]
    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE audit_entries DISABLE TRIGGER audit_entries_immutable_row")
        await conn.execute(
            "UPDATE audit_entries SET agent_id = 'agent_evil' WHERE ledger_id = $1",
            entries[1]["ledger_id"],
        )
        await conn.execute("ALTER TABLE audit_entries ENABLE TRIGGER audit_entries_immutable_row")

    body = (await client.get("/v1/chain/verify", headers=AUTH_A)).json()
    assert body["verified"] is False
    assert body["broken_at_sequence"] == 2

    list_body = (await client.get("/v1/entries", headers=AUTH_A)).json()
    assert list_body["chain_integrity_verified"] is False
