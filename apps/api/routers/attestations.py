"""Supervisory attestation endpoints (FINRA Rule 3110).

POST /v1/attestations                     — record a supervisory decision
GET  /v1/attestations?audit_entry_id=...  — attestation history for an entry
GET  /v1/attestations/queue               — entries awaiting review, oldest first
GET  /v1/attestations/reason-codes        — dropdown taxonomy for the modal
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from models.attestation import (
    REASON_CODE_LABELS,
    AttestationRecord,
    AttestationRequest,
    QueueResponse,
)
from services.attestation import (
    AttestationService,
    EntryNotFoundError,
    NotesRequiredError,
)

router = APIRouter(prefix="/v1", tags=["attestations"])

_service = AttestationService()


def _client_ip(request: Request) -> str:
    # Behind the ALB the original client is the first X-Forwarded-For hop.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


@router.post("/attestations", response_model=AttestationRecord, status_code=201)
async def create_attestation(
    body: AttestationRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> AttestationRecord:
    pool = await get_pool()
    try:
        return await _service.create(
            request=body,
            firm_id=auth.firm_id,
            supervisor_user_id=auth.subject,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            pool=pool,
        )
    except EntryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No such ledger entry."},
        )
    except NotesRequiredError:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "notes_required",
                "message": "OTHER_DOCUMENTED attestations must include notes.",
            },
        )


@router.get("/attestations", response_model=list[AttestationRecord])
async def list_attestations(
    audit_entry_id: str = Query(min_length=1),
    auth: AuthContext = Depends(get_auth_context),
) -> list[AttestationRecord]:
    pool = await get_pool()
    return await _service.list_for_entry(audit_entry_id, auth.firm_id, pool)


@router.get("/attestations/queue", response_model=QueueResponse)
async def pending_queue(
    auth: AuthContext = Depends(get_auth_context),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> QueueResponse:
    pool = await get_pool()
    items, total = await _service.pending_queue(auth.firm_id, limit, offset, pool)
    return QueueResponse(items=items, total_pending=total, limit=limit, offset=offset)


@router.get("/attestations/reason-codes")
async def reason_codes() -> list[dict]:
    return [{"code": code.value, "label": label} for code, label in REASON_CODE_LABELS.items()]
