"""FINRA Rule 3110 supervisory attestation workflow.

Attestations are append-only regulatory records. Re-attestation is allowed
(e.g. ESCALATED, then APPROVED by a senior principal) — the latest decision
drives an entry's review status, and the full sequence is preserved forever.

signature_hash is a SHA-256 over the canonical attestation content INCLUDING
the target entry's hash — binding the attestation to the exact ledger entry
state that was reviewed. Anyone holding the row can recompute and verify it.
"""

import ipaddress
import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from crypto.hasher import hash_payload
from models.attestation import AttestationRecord, AttestationRequest
from services.ledger import generate_ulid


class EntryNotFoundError(Exception):
    """The referenced audit entry does not exist within the caller's firm."""


class NotesRequiredError(Exception):
    """OTHER_DOCUMENTED attestations must carry explanatory notes."""


def canonical_timestamp(dt: datetime) -> str:
    """Fixed-format UTC timestamp for hashing — deterministic regardless of the
    JSON serializer's offset style ('Z' vs '+00:00'). Microsecond precision,
    matching what TIMESTAMPTZ preserves, so the hash is recomputable from
    either the API response or the database row."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def compute_attestation_signature_hash(
    audit_entry_id: str,
    entry_hash: str,
    supervisor_user_id: str,
    supervisor_finra_crd: str,
    supervisor_role: str,
    decision: str,
    reason_code: str,
    notes: str | None,
    attested_at: datetime,
) -> str:
    canonical = {
        "audit_entry_id": audit_entry_id,
        "entry_hash": entry_hash,
        "supervisor_user_id": supervisor_user_id,
        "supervisor_finra_crd": supervisor_finra_crd,
        "supervisor_role": supervisor_role,
        "decision": decision,
        "reason_code": reason_code,
        "notes": notes,
        "attested_at": canonical_timestamp(attested_at),
    }
    return hash_payload(json.dumps(canonical, sort_keys=True, separators=(",", ":")))


class AttestationService:
    async def create(
        self,
        request: AttestationRequest,
        firm_id: str,
        supervisor_user_id: str,
        ip_address: str,
        user_agent: str | None,
        pool: asyncpg.Pool,
    ) -> AttestationRecord:
        if request.reason_code.value == "OTHER_DOCUMENTED" and not (request.notes or "").strip():
            raise NotesRequiredError()

        async with pool.acquire() as conn:
            # Firm scoping happens here: the entry must belong to the caller's firm.
            entry = await conn.fetchrow(
                "SELECT ledger_id, entry_hash FROM audit_entries "
                "WHERE ledger_id = $1 AND firm_id = $2",
                request.audit_entry_id,
                firm_id,
            )
            if entry is None:
                raise EntryNotFoundError(request.audit_entry_id)

            attested_at = datetime.now(timezone.utc)
            signature_hash = compute_attestation_signature_hash(
                audit_entry_id=request.audit_entry_id,
                entry_hash=entry["entry_hash"],
                supervisor_user_id=supervisor_user_id,
                supervisor_finra_crd=request.supervisor_finra_crd,
                supervisor_role=request.supervisor_role,
                decision=request.decision.value,
                reason_code=request.reason_code.value,
                notes=request.notes,
                attested_at=attested_at,
            )
            attestation_id = generate_ulid(prefix="attest_")

            await conn.execute(
                """
                INSERT INTO supervisory_attestations (
                    id, audit_entry_id, supervisor_user_id, supervisor_finra_crd,
                    supervisor_role, decision, reason_code, notes, signature_hash,
                    attested_at, ip_address, user_agent
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                attestation_id, request.audit_entry_id, supervisor_user_id,
                request.supervisor_finra_crd, request.supervisor_role,
                request.decision.value, request.reason_code.value, request.notes,
                signature_hash, attested_at,
                ipaddress.ip_address(ip_address), user_agent,
            )

        return AttestationRecord(
            id=attestation_id,
            audit_entry_id=request.audit_entry_id,
            supervisor_user_id=supervisor_user_id,
            supervisor_finra_crd=request.supervisor_finra_crd,
            supervisor_role=request.supervisor_role,
            decision=request.decision,
            reason_code=request.reason_code,
            notes=request.notes,
            signature_hash=signature_hash,
            attested_at=attested_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def list_for_entry(
        self, audit_entry_id: str, firm_id: str, pool: asyncpg.Pool
    ) -> list[AttestationRecord]:
        rows = await pool.fetch(
            """
            SELECT a.* FROM supervisory_attestations a
            JOIN audit_entries e ON e.ledger_id = a.audit_entry_id
            WHERE a.audit_entry_id = $1 AND e.firm_id = $2
            ORDER BY a.attested_at ASC
            """,
            audit_entry_id,
            firm_id,
        )
        return [_record_from_row(r) for r in rows]

    async def pending_queue(
        self, firm_id: str, limit: int, offset: int, pool: asyncpg.Pool
    ) -> tuple[list[dict[str, Any]], int]:
        """Entries requiring attestation with none recorded — oldest first,
        because regulators measure supervisory timeliness."""
        where = """
            e.firm_id = $1 AND e.requires_attestation
            AND NOT EXISTS (
                SELECT 1 FROM supervisory_attestations a
                WHERE a.audit_entry_id = e.ledger_id
            )
        """
        rows = await pool.fetch(
            f"""
            SELECT e.ledger_id, e.sequence_number, e.timestamp_utc, e.agent_id,
                   e.registered_rep_id, e.action_type, e.action_name,
                   e.risk_score, e.risk_tier, e.risk_flags
            FROM audit_entries e
            WHERE {where}
            ORDER BY e.timestamp_utc ASC
            LIMIT $2 OFFSET $3
            """,
            firm_id, limit, offset,
        )
        total = await pool.fetchval(
            f"SELECT COUNT(*) FROM audit_entries e WHERE {where}", firm_id
        )
        now = datetime.now(timezone.utc)
        return (
            [
                {
                    "ledger_id": r["ledger_id"],
                    "sequence_number": r["sequence_number"],
                    "timestamp_utc": r["timestamp_utc"],
                    "seconds_pending": (now - r["timestamp_utc"]).total_seconds(),
                    "agent_id": r["agent_id"],
                    "registered_rep_id": r["registered_rep_id"],
                    "action_type": r["action_type"],
                    "action_name": r["action_name"],
                    "risk_score": float(r["risk_score"]),
                    "risk_tier": r["risk_tier"],
                    "risk_flags": json.loads(r["risk_flags"]),
                }
                for r in rows
            ],
            total,
        )


def _record_from_row(row: asyncpg.Record) -> AttestationRecord:
    return AttestationRecord(
        id=row["id"],
        audit_entry_id=row["audit_entry_id"],
        supervisor_user_id=row["supervisor_user_id"],
        supervisor_finra_crd=row["supervisor_finra_crd"],
        supervisor_role=row["supervisor_role"],
        decision=row["decision"],
        reason_code=row["reason_code"],
        notes=row["notes"],
        signature_hash=row["signature_hash"],
        attested_at=row["attested_at"],
        ip_address=str(row["ip_address"]),
        user_agent=row["user_agent"],
    )
