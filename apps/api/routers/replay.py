"""GET /v1/entries/{ledger_id}/replay — SEC Rule 206(4)-7 policy replay.

Reconstructs the policy version in force at the entry's execution timestamp
and reports whether it matches the hash the entry recorded. Firm-scoped: a
cross-firm ledger_id is a 404, never a cross-firm read.
"""

from fastapi import APIRouter, Depends, HTTPException, Path

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from models.policy import ReplayResolution
from services.replay import EntryNotFoundError, ReplayService

router = APIRouter(prefix="/v1", tags=["replay"])

_service = ReplayService()


@router.get("/entries/{ledger_id}/replay", response_model=ReplayResolution)
async def replay_entry(
    ledger_id: str = Path(min_length=1),
    auth: AuthContext = Depends(get_auth_context),
) -> ReplayResolution:
    pool = await get_pool()
    try:
        return await _service.replay_entry(ledger_id, auth.firm_id, pool)
    except EntryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No such ledger entry."},
        )
