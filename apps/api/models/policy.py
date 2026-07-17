"""Pydantic models for the policy registry and SEC Rule 206(4)-7 replay.

A policy has many versions; each version is content-addressed (policy_hash),
WORM-stored, and carries an effective window. Replay reconstructs the version
in force at an audit entry's execution timestamp and cross-checks it against
the hash the entry recorded at the time.
"""

from datetime import datetime
from enum import Enum

from pydantic import Field

from models.audit_entry import StrictModel


class PolicyCreateRequest(StrictModel):
    """Upload a new policy version. version_number is assigned server-side
    (previous current version, if any, is superseded as of effective_at)."""

    policy_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1)
    # When this version takes effect. Defaults to now; may be backdated to
    # record a policy that was already in force.
    effective_at: datetime | None = None


class PolicyVersionRecord(StrictModel):
    id: str
    firm_id: str
    policy_id: str
    name: str | None
    version_number: int
    policy_hash: str
    content_s3_key: str
    effective_at: datetime
    superseded_at: datetime | None
    created_by_user_id: str
    created_at: datetime


class PolicyVersionDetail(PolicyVersionRecord):
    """A version plus its immutable content, read back from WORM storage."""

    content: str


class PolicySummary(StrictModel):
    """One row per logical policy in the registry list — its latest version."""

    policy_id: str
    name: str | None
    latest_version_id: str
    latest_version_number: int
    latest_policy_hash: str
    version_count: int
    first_effective_at: datetime
    latest_effective_at: datetime


class ReplayStatus(str, Enum):
    """Verdict of a point-in-time policy reconstruction.

    RECONSTRUCTED_CONSISTENT — the version in force at the execution timestamp
        was found in the registry and its content hash matches the hash the
        entry recorded. The record is corroborated end-to-end.
    RECONSTRUCTION_DISCREPANCY — a policy version was reconstructed for the
        timestamp, but its hash does not match what the entry recorded (or no
        version was in force at that instant). Requires escalation.
    RECORDED_NOT_IN_REGISTRY — the policy version the entry references is not
        in the registry, so reconstruction is impossible; only the recorded
        hash is on the record (common for externally managed policies).
    """

    RECONSTRUCTED_CONSISTENT = "RECONSTRUCTED_CONSISTENT"
    RECONSTRUCTION_DISCREPANCY = "RECONSTRUCTION_DISCREPANCY"
    RECORDED_NOT_IN_REGISTRY = "RECORDED_NOT_IN_REGISTRY"


class EffectiveWindow(StrictModel):
    effective_at: datetime
    superseded_at: datetime | None


class ReplayResolution(StrictModel):
    """Full SEC 206(4)-7 replay evidence for a single audit entry."""

    ledger_id: str
    execution_timestamp_utc: datetime
    execution_unix_ns: int
    recorded_policy_version_id: str
    recorded_policy_version_hash: str

    status: ReplayStatus
    hash_match: bool

    # The version reconstructed as in force at the execution timestamp
    # (temporal resolution). None when nothing was in force / not registered.
    resolved_version: PolicyVersionRecord | None
    effective_window: EffectiveWindow | None
    # The immutable policy text as it stood at execution time.
    policy_content: str | None
