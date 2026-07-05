"""End-to-end Phase 1 integration tests.

Requires the local stack (Postgres + LocalStack S3):
    docker compose -f infrastructure/docker-compose.yml up -d
"""

import asyncio
import gzip
import json

import asyncpg
import boto3
import pytest

from crypto.hasher import GENESIS_HASH, compute_entry_hash, hash_payload
from crypto.signer import LedgerSigner
from models.audit_entry import (
    ActionInfo,
    AgentInfo,
    IngestEvent,
    PolicyInfo,
    RiskAssessment,
    RiskTier,
    SessionInfo,
)
from services.ledger import LedgerService


def make_event(firm_id: str = "firm_acme", i: int = 0, **risk_kwargs) -> IngestEvent:
    return IngestEvent(
        firm_id=firm_id,
        agent=AgentInfo(agent_id="agent_rebalancer", framework="langchain"),
        session=SessionInfo(session_id=f"sess_{i:04d}", registered_rep_id="rep_777"),
        action=ActionInfo(action_type="tool_call", action_name="portfolio_rebalance"),
        policy=PolicyInfo(
            policy_version_id="polv_001",
            policy_version_hash=hash_payload({"policy": "v1"}),
        ),
        risk=RiskAssessment(**risk_kwargs) if risk_kwargs else RiskAssessment(),
        input={"portfolio_id": f"pf_{i}", "target_allocation": {"equities": 0.6}},
        output={"orders_placed": i + 1, "status": "executed"},
        reasoning_trace=f"Rebalanced portfolio pf_{i} toward target allocation.",
    )


@pytest.fixture
def ledger(worm_bucket):
    return LedgerService(bucket=worm_bucket)


async def test_ingest_returns_chained_signed_entry(ledger, pool):
    entry = await ledger.ingest(make_event(), pool)

    assert entry["ledger_id"].startswith("entry_")
    assert entry["sequence_number"] == 1
    assert entry["previous_hash"] == GENESIS_HASH
    assert entry["worm_object_lock_mode"] == "COMPLIANCE"

    # entry_hash is recomputable from the entry's own fields
    recomputed = compute_entry_hash(
        previous_hash=entry["previous_hash"],
        sequence_number=entry["sequence_number"],
        timestamp_unix_ns=entry["timestamp"]["unix_ns"],
        input_payload_hash=entry["input_payload_hash"],
        output_payload_hash=entry["output_payload_hash"],
        policy_version_hash=entry["policy"]["policy_version_hash"],
        agent_id=entry["agent"]["agent_id"],
        session_id=entry["session"]["session_id"],
    )
    assert recomputed == entry["entry_hash"]

    # platform signature verifies against the platform public key
    signer = LedgerSigner.get()
    assert signer.verify(entry["entry_hash"], entry["platform_signature"]) is True


async def test_chain_links_across_entries(ledger, pool):
    first = await ledger.ingest(make_event(i=1), pool)
    second = await ledger.ingest(make_event(i=2), pool)
    third = await ledger.ingest(make_event(i=3), pool)

    assert [e["sequence_number"] for e in (first, second, third)] == [1, 2, 3]
    assert second["previous_hash"] == first["entry_hash"]
    assert third["previous_hash"] == second["entry_hash"]

    result = await ledger.verify_chain("firm_acme", pool)
    assert result == {"verified": True, "entries_checked": 3, "broken_at_sequence": None}


async def test_chains_are_per_firm(ledger, pool):
    await ledger.ingest(make_event(firm_id="firm_a", i=1), pool)
    await ledger.ingest(make_event(firm_id="firm_a", i=2), pool)
    b1 = await ledger.ingest(make_event(firm_id="firm_b", i=1), pool)

    # firm_b starts its own chain at sequence 1 from the genesis hash
    assert b1["sequence_number"] == 1
    assert b1["previous_hash"] == GENESIS_HASH
    assert (await ledger.verify_chain("firm_a", pool))["verified"] is True
    assert (await ledger.verify_chain("firm_b", pool))["verified"] is True


async def test_entry_read_back_from_worm_s3(ledger, pool, worm_bucket):
    written = await ledger.ingest(make_event(), pool)
    loaded = await ledger.get_entry(written["ledger_id"], pool)

    assert loaded is not None
    assert loaded["entry_hash"] == written["entry_hash"]
    assert loaded["input"] == written["input"]
    assert loaded["output"] == written["output"]

    # payload hashes recompute correctly from the stored payloads
    assert hash_payload(loaded["input"]) == loaded["input_payload_hash"]
    assert hash_payload(loaded["output"]) == loaded["output_payload_hash"]

    # the S3 object itself carries COMPLIANCE-mode Object Lock
    s3 = boto3.client("s3")
    head = s3.head_object(Bucket=worm_bucket, Key=written["worm_s3_key"])
    assert head["ObjectLockMode"] == "COMPLIANCE"
    assert "ObjectLockRetainUntilDate" in head


async def test_get_entry_unknown_ledger_id_returns_none(ledger, pool):
    assert await ledger.get_entry("entry_DOESNOTEXIST", pool) is None


async def test_audit_entries_reject_update_and_delete(ledger, pool):
    entry = await ledger.ingest(make_event(), pool)

    with pytest.raises(asyncpg.PostgresError, match="IMMUTABLE RECORDKEEPING"):
        await pool.execute(
            "UPDATE audit_entries SET risk_tier = 'LOW' WHERE ledger_id = $1",
            entry["ledger_id"],
        )
    with pytest.raises(asyncpg.PostgresError, match="IMMUTABLE RECORDKEEPING"):
        await pool.execute(
            "DELETE FROM audit_entries WHERE ledger_id = $1", entry["ledger_id"]
        )
    with pytest.raises(asyncpg.PostgresError):
        await pool.execute("TRUNCATE audit_entries CASCADE")

    # the record is still there, chain intact
    assert (await ledger.verify_chain("firm_acme", pool))["verified"] is True


async def test_tampered_row_breaks_chain_verification(ledger, pool):
    """If audit metadata were somehow altered at rest, verify_chain must catch it.

    The immutability triggers block SQL tampering, so simulate at-rest tampering
    by disabling the trigger as a superuser would — exactly the adversary the
    hash chain exists to expose.
    """
    await ledger.ingest(make_event(i=1), pool)
    tampered = await ledger.ingest(make_event(i=2), pool)
    await ledger.ingest(make_event(i=3), pool)

    async with pool.acquire() as conn:
        await conn.execute("ALTER TABLE audit_entries DISABLE TRIGGER audit_entries_immutable_row")
        await conn.execute(
            "UPDATE audit_entries SET input_payload_hash = $1 WHERE ledger_id = $2",
            "sha256:" + "f" * 64,
            tampered["ledger_id"],
        )
        await conn.execute("ALTER TABLE audit_entries ENABLE TRIGGER audit_entries_immutable_row")

    result = await ledger.verify_chain("firm_acme", pool)
    assert result["verified"] is False
    assert result["broken_at_sequence"] == tampered["sequence_number"]


async def test_concurrent_ingest_produces_unbroken_chain(ledger, pool):
    """10 concurrent ingests for one firm must serialize into sequences 1..10."""
    entries = await asyncio.gather(
        *(ledger.ingest(make_event(i=i), pool) for i in range(10))
    )
    assert sorted(e["sequence_number"] for e in entries) == list(range(1, 11))
    result = await ledger.verify_chain("firm_acme", pool)
    assert result == {"verified": True, "entries_checked": 10, "broken_at_sequence": None}


async def test_high_risk_entry_flags_attestation(ledger, pool):
    await ledger.ingest(
        make_event(
            risk_score=0.91,
            risk_tier=RiskTier.CRITICAL,
            risk_flags=["large_notional", "off_hours_trading"],
            requires_supervisor_review=True,
        ),
        pool,
    )
    row = await pool.fetchrow(
        "SELECT risk_score, risk_tier, risk_flags, requires_attestation "
        "FROM audit_entries WHERE firm_id = 'firm_acme'"
    )
    assert float(row["risk_score"]) == 0.91
    assert row["risk_tier"] == "CRITICAL"
    assert json.loads(row["risk_flags"]) == ["large_notional", "off_hours_trading"]
    assert row["requires_attestation"] is True


async def test_worm_object_is_gzipped_canonical_json(ledger, pool, worm_bucket):
    written = await ledger.ingest(make_event(), pool)
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=worm_bucket, Key=written["worm_s3_key"])
    payload = json.loads(gzip.decompress(obj["Body"].read()))
    assert payload["@context"] == "https://trailmark.ai/schema/v1/audit-entry"
    assert payload["@type"] == "AgentAuditEntry"
    assert payload["ledger_id"] == written["ledger_id"]
