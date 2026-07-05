"""Pydantic models for FINRA Rule 3110 supervisory attestations."""

from datetime import datetime
from enum import Enum

from pydantic import Field

from models.audit_entry import RiskTier, StrictModel


class AttestationDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class ReasonCode(str, Enum):
    """Supervisory review reason codes (FINRA 3110 written-procedures taxonomy).

    Rendered as the dropdown in the attestation modal; every attestation must
    carry one. OTHER_DOCUMENTED requires notes.
    """

    APPROVED_POLICY_CONSISTENT = "APPROVED_POLICY_CONSISTENT"
    APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"
    REJECTED_POLICY_VIOLATION = "REJECTED_POLICY_VIOLATION"
    REJECTED_RISK_LIMIT_EXCEEDED = "REJECTED_RISK_LIMIT_EXCEEDED"
    REJECTED_INSUFFICIENT_DOCUMENTATION = "REJECTED_INSUFFICIENT_DOCUMENTATION"
    ESCALATED_TO_COMPLIANCE = "ESCALATED_TO_COMPLIANCE"
    ESCALATED_TO_LEGAL = "ESCALATED_TO_LEGAL"
    OTHER_DOCUMENTED = "OTHER_DOCUMENTED"


REASON_CODE_LABELS: dict[ReasonCode, str] = {
    ReasonCode.APPROVED_POLICY_CONSISTENT: "Reviewed — consistent with firm policy",
    ReasonCode.APPROVED_WITH_CONDITIONS: "Approved with documented conditions",
    ReasonCode.REJECTED_POLICY_VIOLATION: "Rejected — violates firm policy",
    ReasonCode.REJECTED_RISK_LIMIT_EXCEEDED: "Rejected — exceeds risk limits",
    ReasonCode.REJECTED_INSUFFICIENT_DOCUMENTATION: "Rejected — insufficient documentation",
    ReasonCode.ESCALATED_TO_COMPLIANCE: "Escalated to compliance department",
    ReasonCode.ESCALATED_TO_LEGAL: "Escalated to legal counsel",
    ReasonCode.OTHER_DOCUMENTED: "Other — see notes",
}


class AttestationRequest(StrictModel):
    audit_entry_id: str = Field(min_length=1)
    decision: AttestationDecision
    reason_code: ReasonCode
    notes: str | None = None
    # In production these derive from the Clerk user's profile; accepted in the
    # body until user-metadata sync lands, and always recorded verbatim.
    supervisor_finra_crd: str = Field(min_length=1)
    supervisor_role: str = Field(min_length=1)


class AttestationRecord(StrictModel):
    id: str
    audit_entry_id: str
    supervisor_user_id: str
    supervisor_finra_crd: str
    supervisor_role: str
    decision: AttestationDecision
    reason_code: ReasonCode
    notes: str | None
    signature_hash: str
    attested_at: datetime
    ip_address: str
    user_agent: str | None


class QueueItem(StrictModel):
    """One entry awaiting supervisory review."""

    ledger_id: str
    sequence_number: int
    timestamp_utc: datetime
    seconds_pending: float
    agent_id: str
    registered_rep_id: str | None
    action_type: str
    action_name: str
    risk_score: float
    risk_tier: RiskTier
    risk_flags: list[str]


class QueueResponse(StrictModel):
    items: list[QueueItem]
    total_pending: int
    limit: int
    offset: int
