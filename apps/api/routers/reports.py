"""POST /v1/reports/sec-17a4 — regulation-formatted examination evidence."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from auth import AuthContext, get_auth_context
from db.connection import get_pool
from services.reports import ReportRequestData, ReportService

router = APIRouter(prefix="/v1", tags=["reports"])

_service = ReportService()


class ReportRequest(BaseModel):
    period_from: datetime
    period_to: datetime
    # Firm display identity for the report header. Optional until the firm
    # registry lands; recorded verbatim.
    firm_name: str | None = Field(default=None, max_length=200)
    firm_crd: str | None = Field(default=None, max_length=40)


@router.post("/reports/sec-17a4")
async def generate_sec_17a4(
    body: ReportRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> Response:
    if body.period_to <= body.period_from:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_period", "message": "period_to must be after period_from."},
        )
    pool = await get_pool()
    pdf, attestation = await _service.generate_sec_17a4(
        ReportRequestData(
            firm_id=auth.firm_id,
            firm_name=body.firm_name or auth.firm_id,
            firm_crd=body.firm_crd or "—",
            period_from=body.period_from,
            period_to=body.period_to,
        ),
        pool,
    )
    filename = (
        f"trailmark-sec17a4-{auth.firm_id}-"
        f"{body.period_from:%Y%m%d}-{body.period_to:%Y%m%d}.pdf"
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Programmatic verification without parsing the PDF:
            "X-TrailMark-Report-Hash": attestation["report_hash"],
            "X-TrailMark-Report-Signature": attestation["signature"],
        },
    )
