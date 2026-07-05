"""Attestation workflow tests (FINRA 3110)."""

from datetime import datetime

import asyncpg
import pytest

from services.attestation import compute_attestation_signature_hash
from tests.test_api import AUTH_A, AUTH_B, FIRM_A, client, ingest_one  # noqa: F401

HIGH_RISK = dict(
    risk_score=0.9,
    risk_tier="HIGH",
    risk_flags=["large_notional"],
    requires_supervisor_review=True,
)


def attestation_body(ledger_id: str, **overrides) -> dict:
    return {
        "audit_entry_id": ledger_id,
        "decision": "APPROVED",
        "reason_code": "APPROVED_POLICY_CONSISTENT",
        "notes": "Reviewed order size against firm limits.",
        "supervisor_finra_crd": "1234567",
        "supervisor_role": "Series 24 Principal",
        **overrides,
    }


async def attest(client, ledger_id: str, headers=AUTH_A, **overrides):
    return await client.post(
        "/v1/attestations", json=attestation_body(ledger_id, **overrides), headers=headers
    )


# ---------------------------------------------------------------- create

async def test_attestation_roundtrip(client):
    entry = await ingest_one(client, **HIGH_RISK)
    resp = await attest(client, entry["ledger_id"])
    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert record["id"].startswith("attest_")
    assert record["decision"] == "APPROVED"
    assert record["supervisor_user_id"] == AUTH_A["Authorization"].removeprefix("Bearer ")
    assert record["ip_address"]  # captured, NOT NULL
    assert record["signature_hash"].startswith("sha256:")

    # signature_hash is recomputable by an external verifier holding only the
    # serialized record and the target entry hash
    recomputed = compute_attestation_signature_hash(
        audit_entry_id=record["audit_entry_id"],
        entry_hash=entry["entry_hash"],
        supervisor_user_id=record["supervisor_user_id"],
        supervisor_finra_crd=record["supervisor_finra_crd"],
        supervisor_role=record["supervisor_role"],
        decision=record["decision"],
        reason_code=record["reason_code"],
        notes=record["notes"],
        attested_at=datetime.fromisoformat(record["attested_at"]),
    )
    assert recomputed == record["signature_hash"]


async def test_attestation_flips_entry_status(client):
    entry = await ingest_one(client, **HIGH_RISK)
    before = (await client.get("/v1/entries", headers=AUTH_A)).json()
    assert before["entries"][0]["status"] == "PENDING_REVIEW"

    await attest(client, entry["ledger_id"], decision="REJECTED",
                 reason_code="REJECTED_RISK_LIMIT_EXCEEDED")
    after = (await client.get("/v1/entries", headers=AUTH_A)).json()
    assert after["entries"][0]["status"] == "REJECTED"


async def test_reattestation_appends_latest_decision_wins(client):
    entry = await ingest_one(client, **HIGH_RISK)
    r1 = await attest(client, entry["ledger_id"], decision="ESCALATED",
                      reason_code="ESCALATED_TO_COMPLIANCE")
    r2 = await attest(client, entry["ledger_id"], decision="APPROVED",
                      reason_code="APPROVED_WITH_CONDITIONS",
                      notes="Cleared by compliance after escalation.")
    assert r1.status_code == r2.status_code == 201

    history = (
        await client.get("/v1/attestations",
                         params={"audit_entry_id": entry["ledger_id"]}, headers=AUTH_A)
    ).json()
    assert [a["decision"] for a in history] == ["ESCALATED", "APPROVED"]

    status = (await client.get("/v1/entries", headers=AUTH_A)).json()["entries"][0]["status"]
    assert status == "APPROVED"


async def test_attesting_cross_firm_entry_is_404(client):
    entry = await ingest_one(client, **HIGH_RISK)  # firm A
    resp = await attest(client, entry["ledger_id"], headers=AUTH_B)
    assert resp.status_code == 404


async def test_other_documented_requires_notes(client):
    entry = await ingest_one(client, **HIGH_RISK)
    resp = await attest(client, entry["ledger_id"],
                        reason_code="OTHER_DOCUMENTED", notes="   ")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "notes_required"


async def test_invalid_decision_and_reason_code_rejected(client):
    entry = await ingest_one(client, **HIGH_RISK)
    resp = await attest(client, entry["ledger_id"], decision="MAYBE")
    assert resp.status_code == 422
    resp = await attest(client, entry["ledger_id"], reason_code="NOT_A_CODE")
    assert resp.status_code == 422


async def test_attestations_are_append_only(client, pool):
    entry = await ingest_one(client, **HIGH_RISK)
    record = (await attest(client, entry["ledger_id"])).json()
    with pytest.raises(asyncpg.PostgresError, match="IMMUTABLE RECORDKEEPING"):
        await pool.execute(
            "UPDATE supervisory_attestations SET decision = 'REJECTED' WHERE id = $1",
            record["id"],
        )
    with pytest.raises(asyncpg.PostgresError, match="IMMUTABLE RECORDKEEPING"):
        await pool.execute("DELETE FROM supervisory_attestations WHERE id = $1", record["id"])


# ---------------------------------------------------------------- queue

async def test_queue_lists_pending_oldest_first_and_drains(client):
    low = await ingest_one(client, i=1)  # not attestation-required
    first = await ingest_one(client, i=2, **HIGH_RISK)
    second = await ingest_one(client, i=3, **HIGH_RISK)

    queue = (await client.get("/v1/attestations/queue", headers=AUTH_A)).json()
    assert queue["total_pending"] == 2
    ids = [item["ledger_id"] for item in queue["items"]]
    assert ids == [first["ledger_id"], second["ledger_id"]]  # oldest first
    assert low["ledger_id"] not in ids
    assert queue["items"][0]["seconds_pending"] >= 0
    assert queue["items"][0]["risk_flags"] == ["large_notional"]

    await attest(client, first["ledger_id"])
    queue = (await client.get("/v1/attestations/queue", headers=AUTH_A)).json()
    assert queue["total_pending"] == 1
    assert queue["items"][0]["ledger_id"] == second["ledger_id"]


async def test_queue_is_firm_scoped(client):
    await ingest_one(client, firm_id=FIRM_A, i=1, **HIGH_RISK)
    queue_b = (await client.get("/v1/attestations/queue", headers=AUTH_B)).json()
    assert queue_b["total_pending"] == 0


# ---------------------------------------------------------------- reason codes

async def test_reason_codes_taxonomy(client):
    resp = await client.get("/v1/attestations/reason-codes")
    codes = resp.json()
    assert {"code": "APPROVED_POLICY_CONSISTENT",
            "label": "Reviewed — consistent with firm policy"} in codes
    assert len(codes) == 8
