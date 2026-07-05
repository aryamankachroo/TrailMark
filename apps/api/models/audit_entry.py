"""Pydantic models for audit ledger ingestion.

IngestEvent is the wire format accepted by POST /v1/ingest. Validation is
strict (extra fields rejected) — an audit record with unrecognized fields is a
recordkeeping defect, not a convenience.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_REGULATORY_TAGS = ["SEC_17a4", "FINRA_3110"]


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentInfo(StrictModel):
    agent_id: str = Field(min_length=1)
    framework: str = Field(min_length=1)
    agent_version: str | None = None


class SessionInfo(StrictModel):
    session_id: str = Field(min_length=1)
    registered_rep_id: str | None = None


class ActionInfo(StrictModel):
    action_type: str = Field(min_length=1)
    action_name: str = Field(min_length=1)


class PolicyInfo(StrictModel):
    policy_version_id: str = Field(min_length=1)
    policy_version_hash: str = Field(min_length=1)


class RiskAssessment(StrictModel):
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_tier: RiskTier = RiskTier.LOW
    risk_flags: list[str] = Field(default_factory=list)
    requires_supervisor_review: bool = False


class IngestEvent(StrictModel):
    firm_id: str = Field(min_length=1)
    agent: AgentInfo
    session: SessionInfo
    action: ActionInfo
    policy: PolicyInfo
    risk: RiskAssessment = Field(default_factory=RiskAssessment)
    input: dict | str = Field(default_factory=dict)
    output: dict | str = Field(default_factory=dict)
    reasoning_trace: str | None = None
    regulatory_tags: list[str] = Field(
        default_factory=lambda: list(DEFAULT_REGULATORY_TAGS)
    )
