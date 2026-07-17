"""SEC Rule 206(4)-7 policy replay engine.

Reconstructs the exact policy version in force at an audit entry's execution
timestamp and cross-checks it against the policy hash the entry recorded at
the time. This is a genuine reconstruction from the registry's effective
windows — not a lookup of whatever the entry happened to store — so it can
surface discrepancies between what an agent claimed to act under and what was
actually in force.
"""

import asyncpg

from models.policy import (
    EffectiveWindow,
    ReplayResolution,
    ReplayStatus,
)
from services.policy import PolicyService, _record_from_row


class EntryNotFoundError(Exception):
    """No such audit entry within the caller's firm."""


class ReplayService:
    def __init__(self, policy_service: PolicyService | None = None):
        self.policies = policy_service or PolicyService()

    async def replay_entry(
        self, ledger_id: str, firm_id: str, pool: asyncpg.Pool
    ) -> ReplayResolution:
        entry = await pool.fetchrow(
            """
            SELECT ledger_id, timestamp_utc, unix_ns,
                   policy_version_id, policy_version_hash
            FROM audit_entries
            WHERE ledger_id = $1 AND firm_id = $2
            """,
            ledger_id,
            firm_id,
        )
        if entry is None:
            raise EntryNotFoundError(ledger_id)

        recorded_id = entry["policy_version_id"]
        recorded_hash = entry["policy_version_hash"]
        execution_at = entry["timestamp_utc"]

        # Locate the registry entry this record references (to learn its
        # logical policy_id), then reconstruct what was in force at execution.
        referenced = await self.policies.find_by_id_or_hash(
            firm_id, recorded_id, recorded_hash, pool
        )

        resolved = None
        if referenced is not None:
            resolved = await self.policies.resolve_in_force(
                firm_id, referenced["policy_id"], execution_at, pool
            )

        base = {
            "ledger_id": entry["ledger_id"],
            "execution_timestamp_utc": execution_at,
            "execution_unix_ns": entry["unix_ns"],
            "recorded_policy_version_id": recorded_id,
            "recorded_policy_version_hash": recorded_hash,
        }

        # The referenced policy version is not in the registry at all — the
        # record stands on its own hash; reconstruction is impossible.
        if referenced is None:
            return ReplayResolution(
                **base,
                status=ReplayStatus.RECORDED_NOT_IN_REGISTRY,
                hash_match=False,
                resolved_version=None,
                effective_window=None,
                policy_content=None,
            )

        # A policy is registered but nothing was in force at the execution
        # instant (e.g. the action predates the earliest effective_at).
        if resolved is None:
            return ReplayResolution(
                **base,
                status=ReplayStatus.RECONSTRUCTION_DISCREPANCY,
                hash_match=False,
                resolved_version=_record_from_row(referenced),
                effective_window=None,
                policy_content=None,
            )

        hash_match = resolved["policy_hash"] == recorded_hash
        content = await self.policies._read_content(resolved["content_s3_key"])
        return ReplayResolution(
            **base,
            status=(
                ReplayStatus.RECONSTRUCTED_CONSISTENT
                if hash_match
                else ReplayStatus.RECONSTRUCTION_DISCREPANCY
            ),
            hash_match=hash_match,
            resolved_version=_record_from_row(resolved),
            effective_window=EffectiveWindow(
                effective_at=resolved["effective_at"],
                superseded_at=resolved["superseded_at"],
            ),
            policy_content=content,
        )
