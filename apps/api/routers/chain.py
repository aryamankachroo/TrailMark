"""GET /v1/chain/verify — run a full hash-chain verification for the firm."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from services.ledger import LedgerService

router = APIRouter(prefix="/v1", tags=["chain"])

_ledger = LedgerService()


class ChainVerificationResult(BaseModel):
    firm_id: str
    verified: bool
    entries_checked: int
    broken_at_sequence: int | None


@router.get("/chain/verify", response_model=ChainVerificationResult)
async def verify_chain(
    auth: AuthContext = Depends(get_auth_context),
) -> ChainVerificationResult:
    pool = await get_pool()
    result = await _ledger.verify_chain(auth.firm_id, pool)
    return ChainVerificationResult(firm_id=auth.firm_id, **result)
