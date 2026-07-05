"""Ledger service — the core ingestion pipeline.

Every agent action becomes one immutable ledger entry:

    1. Hash the input/output/reasoning payloads (SHA-256, canonical JSON)
    2. Under a per-firm advisory lock, read the previous entry's hash
    3. Compute this entry's hash, chained to the previous one
    4. Sign the entry hash with the platform Ed25519 key
    5. Write the full entry to WORM S3 (Object Lock COMPLIANCE, 7-year retention)
    6. Insert queryable metadata into PostgreSQL (append-only table)

The chain is per firm. Ingestion for a firm is serialized by
pg_advisory_xact_lock — hash chaining is inherently sequential per chain
(entry N needs entry N-1's hash). In production, SQS FIFO (grouped by firm)
provides the same ordering upstream.

Write order is S3-then-Postgres deliberately: a failed Postgres insert can
leave an orphaned WORM object (harmless — over-retention is safe), but a
Postgres row must never exist without its immutable S3 counterpart.
"""

import asyncio
import gzip
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import boto3
from ulid import ULID

from crypto.hasher import GENESIS_HASH, compute_entry_hash, hash_payload
from crypto.signer import LedgerSigner
from models.audit_entry import IngestEvent

RETENTION_YEARS = 7
SCHEMA_CONTEXT = "https://trailmark.ai/schema/v1/audit-entry"


def generate_ulid(prefix: str = "") -> str:
    return f"{prefix}{ULID()}"


class ChainIntegrityError(Exception):
    """Raised when the stored hash chain fails verification."""


class LedgerService:
    def __init__(self, s3_client: Any | None = None, bucket: str | None = None):
        # boto3 honors AWS_ENDPOINT_URL, so local dev/tests point this at
        # LocalStack without code changes.
        self.s3 = s3_client or boto3.client("s3")
        self.bucket = bucket or os.getenv("WORM_BUCKET", "trailmark-worm-dev")

    async def ingest(self, event: IngestEvent, pool: asyncpg.Pool) -> dict:
        """Record one agent action as an immutable, chained, signed ledger entry."""
        # Step 1: hash the payloads
        input_hash = hash_payload(event.input)
        output_hash = hash_payload(event.output)
        reasoning_hash = (
            hash_payload(event.reasoning_trace) if event.reasoning_trace else None
        )

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Step 2: serialize per-firm chain extension. hashtext() maps the
                # firm_id onto an advisory lock key; the lock releases at commit.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))", event.firm_id
                )
                prev = await conn.fetchrow(
                    "SELECT entry_hash, sequence_number FROM audit_entries "
                    "WHERE firm_id = $1 ORDER BY sequence_number DESC LIMIT 1",
                    event.firm_id,
                )
                prev_hash = prev["entry_hash"] if prev else GENESIS_HASH
                seq_number = (prev["sequence_number"] + 1) if prev else 1

                # Step 3: nanosecond-precision timestamp — the forensic anchor
                now = datetime.now(timezone.utc)
                unix_ns = time_ns_from(now)

                # Step 4: compute the chained entry hash
                entry_hash = compute_entry_hash(
                    previous_hash=prev_hash,
                    sequence_number=seq_number,
                    timestamp_unix_ns=unix_ns,
                    input_payload_hash=input_hash,
                    output_payload_hash=output_hash,
                    policy_version_hash=event.policy.policy_version_hash,
                    agent_id=event.agent.agent_id,
                    session_id=event.session.session_id,
                )

                # Step 5: platform signature
                signature = LedgerSigner.get().sign(entry_hash)

                # Step 6: assemble the complete ledger entry
                ledger_id = generate_ulid(prefix="entry_")
                retain_until = now + timedelta(days=365 * RETENTION_YEARS)
                s3_key = (
                    f"worm/{now.year}/{now.month:02d}/{now.day:02d}/{ledger_id}.json.gz"
                )

                entry = {
                    "@context": SCHEMA_CONTEXT,
                    "@type": "AgentAuditEntry",
                    "ledger_id": ledger_id,
                    "sequence_number": seq_number,
                    "previous_hash": prev_hash,
                    "entry_hash": entry_hash,
                    "platform_signature": signature,
                    "timestamp": {"utc": now.isoformat(), "unix_ns": unix_ns},
                    "firm_id": event.firm_id,
                    "agent": event.agent.model_dump(),
                    "session": event.session.model_dump(),
                    "action": event.action.model_dump(),
                    "policy": event.policy.model_dump(),
                    "risk": event.risk.model_dump(mode="json"),
                    "input": event.input,
                    "output": event.output,
                    "reasoning_trace": event.reasoning_trace,
                    "input_payload_hash": input_hash,
                    "output_payload_hash": output_hash,
                    "reasoning_trace_hash": reasoning_hash,
                    "regulatory_tags": event.regulatory_tags,
                    "worm_s3_key": s3_key,
                    "worm_retain_until_date": retain_until.isoformat(),
                    "worm_object_lock_mode": "COMPLIANCE",
                }

                # Step 7: write to WORM S3 — immutable from this moment.
                # COMPLIANCE mode, never GOVERNANCE (governance can be overridden).
                await asyncio.to_thread(
                    self.s3.put_object,
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=gzip.compress(json.dumps(entry, default=str).encode()),
                    ContentType="application/json",
                    ContentEncoding="gzip",
                    ObjectLockMode="COMPLIANCE",
                    ObjectLockRetainUntilDate=retain_until,
                    ServerSideEncryption="aws:kms",
                )

                # Step 8: queryable metadata into the append-only table
                await conn.execute(
                    """
                    INSERT INTO audit_entries (
                        ledger_id, sequence_number, previous_hash, entry_hash,
                        platform_signature, timestamp_utc, unix_ns, firm_id,
                        agent_id, agent_framework, session_id, registered_rep_id,
                        action_type, action_name, input_payload_hash, output_payload_hash,
                        reasoning_trace_hash, risk_score, risk_tier, risk_flags,
                        requires_attestation, policy_version_id, policy_version_hash,
                        worm_s3_key, worm_retain_until, regulatory_tags
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                        $18,$19,$20,$21,$22,$23,$24,$25,$26
                    )
                    """,
                    ledger_id, seq_number, prev_hash, entry_hash, signature,
                    now, unix_ns, event.firm_id,
                    event.agent.agent_id, event.agent.framework,
                    event.session.session_id, event.session.registered_rep_id,
                    event.action.action_type, event.action.action_name,
                    input_hash, output_hash, reasoning_hash,
                    event.risk.risk_score, event.risk.risk_tier.value,
                    json.dumps(event.risk.risk_flags),
                    event.risk.requires_supervisor_review,
                    event.policy.policy_version_id, event.policy.policy_version_hash,
                    s3_key, retain_until, event.regulatory_tags,
                )

        return entry

    async def get_entry(self, ledger_id: str, pool: asyncpg.Pool) -> dict | None:
        """Load the full immutable entry from WORM S3 by ledger_id."""
        row = await pool.fetchrow(
            "SELECT worm_s3_key FROM audit_entries WHERE ledger_id = $1", ledger_id
        )
        if row is None:
            return None
        obj = await asyncio.to_thread(
            self.s3.get_object, Bucket=self.bucket, Key=row["worm_s3_key"]
        )
        return json.loads(gzip.decompress(obj["Body"].read()))

    async def verify_chain(self, firm_id: str, pool: asyncpg.Pool) -> dict:
        """Recompute and verify the full hash chain for a firm.

        This is a REAL verification — every entry hash is recomputed from the
        stored fields and every previous_hash link is checked. UI integrity
        badges must be driven by this result, never hardcoded.
        """
        rows = await pool.fetch(
            """
            SELECT sequence_number, previous_hash, entry_hash, unix_ns,
                   input_payload_hash, output_payload_hash, policy_version_hash,
                   agent_id, session_id
            FROM audit_entries WHERE firm_id = $1 ORDER BY sequence_number ASC
            """,
            firm_id,
        )
        expected_prev = GENESIS_HASH
        expected_seq = 1
        for row in rows:
            broken = {
                "verified": False,
                "entries_checked": len(rows),
                "broken_at_sequence": row["sequence_number"],
            }
            if row["sequence_number"] != expected_seq:
                return broken
            if row["previous_hash"] != expected_prev:
                return broken
            recomputed = compute_entry_hash(
                previous_hash=row["previous_hash"],
                sequence_number=row["sequence_number"],
                timestamp_unix_ns=row["unix_ns"],
                input_payload_hash=row["input_payload_hash"],
                output_payload_hash=row["output_payload_hash"],
                policy_version_hash=row["policy_version_hash"],
                agent_id=row["agent_id"],
                session_id=row["session_id"],
            )
            if recomputed != row["entry_hash"]:
                return broken
            expected_prev = row["entry_hash"]
            expected_seq += 1
        return {
            "verified": True,
            "entries_checked": len(rows),
            "broken_at_sequence": None,
        }


def time_ns_from(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)
