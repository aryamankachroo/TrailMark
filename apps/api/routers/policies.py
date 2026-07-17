"""Policy registry endpoints (SEC Rule 206(4)-7 foundation).

POST /v1/policies                      — register a new policy version
GET  /v1/policies                      — registry: one row per policy (latest)
GET  /v1/policies/{policy_id}/versions — full version history for a policy
GET  /v1/policies/versions/{id}        — a version plus its immutable content

All queries are scoped to the authenticated firm.
"""

from fastapi import APIRouter, Depends, HTTPException, Path

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from models.policy import (
    PolicyCreateRequest,
    PolicySummary,
    PolicyVersionDetail,
    PolicyVersionRecord,
)
from services.policy import DuplicatePolicyError, PolicyNotFoundError, PolicyService

router = APIRouter(prefix="/v1", tags=["policies"])

_service = PolicyService()


@router.post("/policies", response_model=PolicyVersionRecord, status_code=201)
async def create_policy_version(
    body: PolicyCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> PolicyVersionRecord:
    pool = await get_pool()
    try:
        return await _service.create_version(
            req=body,
            firm_id=auth.firm_id,
            user_id=auth.subject,
            pool=pool,
        )
    except DuplicatePolicyError:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_policy",
                "message": "This exact policy content is already on the record. "
                "A new version must have different content.",
            },
        )


@router.get("/policies", response_model=list[PolicySummary])
async def list_policies(
    auth: AuthContext = Depends(get_auth_context),
) -> list[PolicySummary]:
    pool = await get_pool()
    return await _service.list_policies(auth.firm_id, pool)


@router.get("/policies/{policy_id}/versions", response_model=list[PolicyVersionRecord])
async def list_policy_versions(
    policy_id: str = Path(min_length=1),
    auth: AuthContext = Depends(get_auth_context),
) -> list[PolicyVersionRecord]:
    pool = await get_pool()
    return await _service.list_versions(policy_id, auth.firm_id, pool)


@router.get("/policies/versions/{version_id}", response_model=PolicyVersionDetail)
async def get_policy_version(
    version_id: str = Path(min_length=1),
    auth: AuthContext = Depends(get_auth_context),
) -> PolicyVersionDetail:
    pool = await get_pool()
    try:
        return await _service.get_version(version_id, auth.firm_id, pool)
    except PolicyNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No such policy version."},
        )
