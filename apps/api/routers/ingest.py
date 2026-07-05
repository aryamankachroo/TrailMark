"""POST /v1/ingest — record one agent action as an immutable ledger entry."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from models.audit_entry import IngestEvent
from services.ledger import LedgerService

router = APIRouter(prefix="/v1", tags=["ingest"])

_ledger = LedgerService()


class IngestResponse(BaseModel):
    ledger_id: str
    entry_hash: str
    sequence_number: int
    timestamp_utc: str


@router.post("/ingest", response_model=IngestResponse, status_code=201)
async def ingest(
    event: IngestEvent,
    auth: AuthContext = Depends(get_auth_context),
) -> IngestResponse:
    # Firm scoping: a token may only write to its own firm's ledger.
    if event.firm_id != auth.firm_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "firm_mismatch",
                "message": "Event firm_id does not match the authenticated firm.",
            },
        )
    pool = await get_pool()
    entry = await _ledger.ingest(event, pool)
    return IngestResponse(
        ledger_id=entry["ledger_id"],
        entry_hash=entry["entry_hash"],
        sequence_number=entry["sequence_number"],
        timestamp_utc=entry["timestamp"]["utc"],
    )
