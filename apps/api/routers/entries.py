"""GET /v1/entries — search the audit ledger; GET /v1/entries/{ledger_id} — full WORM record.

All queries are scoped to the authenticated firm. The list response's
chain_integrity_verified flag is the result of a REAL chain verification run
over the firm's ledger (constraint: never fake the integrity badge).
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from models.audit_entry import RiskTier
from services.ledger import LedgerService

router = APIRouter(prefix="/v1", tags=["entries"])

_ledger = LedgerService()

# Derived review status for the dashboard's status badge.
EntryStatus = Literal["AUTO_APPROVED", "PENDING_REVIEW", "APPROVED", "REJECTED", "ESCALATED"]


class EntrySummary(BaseModel):
    ledger_id: str
    sequence_number: int
    timestamp_utc: datetime
    agent_id: str
    agent_framework: str
    registered_rep_id: str | None
    action_type: str
    action_name: str
    risk_score: float
    risk_tier: RiskTier
    requires_attestation: bool
    status: EntryStatus
    entry_hash: str


class EntryListResponse(BaseModel):
    entries: list[EntrySummary]
    total: int
    limit: int
    offset: int
    chain_integrity_verified: bool


@router.get("/entries", response_model=EntryListResponse)
async def list_entries(
    auth: AuthContext = Depends(get_auth_context),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    agent_id: str | None = Query(None),
    risk_tier: RiskTier | None = Query(None),
    requires_attestation: bool | None = Query(None),
    action_name: str | None = Query(None, description="Substring match on action name"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> EntryListResponse:
    conditions = ["e.firm_id = $1"]
    params: list = [auth.firm_id]

    def add(condition_template: str, value) -> None:
        params.append(value)
        conditions.append(condition_template.format(n=len(params)))

    if date_from is not None:
        add("e.timestamp_utc >= ${n}", date_from)
    if date_to is not None:
        add("e.timestamp_utc <= ${n}", date_to)
    if agent_id is not None:
        add("e.agent_id = ${n}", agent_id)
    if risk_tier is not None:
        add("e.risk_tier = ${n}", risk_tier.value)
    if requires_attestation is not None:
        add("e.requires_attestation = ${n}", requires_attestation)
    if action_name is not None:
        add("e.action_name ILIKE ${n}", f"%{action_name}%")

    where = " AND ".join(conditions)
    params_page = [*params, limit, offset]

    pool = await get_pool()
    rows = await pool.fetch(
        f"""
        SELECT e.ledger_id, e.sequence_number, e.timestamp_utc, e.agent_id,
               e.agent_framework, e.registered_rep_id, e.action_type, e.action_name,
               e.risk_score, e.risk_tier, e.requires_attestation, e.entry_hash,
               a.decision AS attestation_decision
        FROM audit_entries e
        LEFT JOIN LATERAL (
            SELECT decision FROM supervisory_attestations
            WHERE audit_entry_id = e.ledger_id
            ORDER BY attested_at DESC LIMIT 1
        ) a ON TRUE
        WHERE {where}
        ORDER BY e.timestamp_utc DESC, e.sequence_number DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params_page,
    )
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM audit_entries e WHERE {where}", *params
    )
    chain = await _ledger.verify_chain(auth.firm_id, pool)

    return EntryListResponse(
        entries=[
            EntrySummary(
                ledger_id=r["ledger_id"],
                sequence_number=r["sequence_number"],
                timestamp_utc=r["timestamp_utc"],
                agent_id=r["agent_id"],
                agent_framework=r["agent_framework"],
                registered_rep_id=r["registered_rep_id"],
                action_type=r["action_type"],
                action_name=r["action_name"],
                risk_score=float(r["risk_score"]),
                risk_tier=RiskTier(r["risk_tier"]),
                requires_attestation=r["requires_attestation"],
                status=_derive_status(r["requires_attestation"], r["attestation_decision"]),
                entry_hash=r["entry_hash"],
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        chain_integrity_verified=chain["verified"],
    )


def _derive_status(requires_attestation: bool, decision: str | None) -> EntryStatus:
    if not requires_attestation:
        return "AUTO_APPROVED"
    if decision is None:
        return "PENDING_REVIEW"
    return {"APPROVED": "APPROVED", "REJECTED": "REJECTED", "ESCALATED": "ESCALATED"}[decision]


@router.get("/entries/{ledger_id}")
async def get_entry(
    ledger_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    pool = await get_pool()
    # Scope the lookup to the firm BEFORE touching S3; cross-firm ids are a 404
    # (not 403 — do not leak that the ledger_id exists).
    row = await pool.fetchrow(
        "SELECT ledger_id FROM audit_entries WHERE ledger_id = $1 AND firm_id = $2",
        ledger_id,
        auth.firm_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No such ledger entry."},
        )
    entry = await _ledger.get_entry(ledger_id, pool)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No such ledger entry."},
        )
    return entry
