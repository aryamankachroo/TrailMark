"""Policy replay integration tests (SEC Rule 206(4)-7).

The core property under test: replay reconstructs the policy version in force
at an entry's *execution timestamp* from the registry's effective windows, and
cross-checks it against the hash the entry recorded — independently of what the
entry stored.

Requires the local stack (Postgres + LocalStack S3):
    docker compose -f infrastructure/docker-compose.yml up -d
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto.hasher import hash_payload
from models.audit_entry import (
    ActionInfo,
    AgentInfo,
    IngestEvent,
    PolicyInfo,
    SessionInfo,
)
from models.policy import PolicyCreateRequest, ReplayStatus
from services.ledger import LedgerService
from services.policy import PolicyService
from services.replay import EntryNotFoundError, ReplayService


@pytest.fixture
def ledger(worm_bucket):
    return LedgerService(bucket=worm_bucket)


@pytest.fixture
def policies(worm_bucket):
    return PolicyService(bucket=worm_bucket)


@pytest.fixture
def replay(policies):
    return ReplayService(policy_service=policies)


def make_event(firm_id, policy_version_id, policy_version_hash, i=0):
    return IngestEvent(
        firm_id=firm_id,
        agent=AgentInfo(agent_id="agent_x", framework="langchain"),
        session=SessionInfo(session_id=f"sess_{i}"),
        action=ActionInfo(action_type="decision", action_name="trade_recommendation"),
        policy=PolicyInfo(
            policy_version_id=policy_version_id,
            policy_version_hash=policy_version_hash,
        ),
        input={"i": i},
        output={"ok": True},
    )


async def _register(policies, pool, content, effective_at=None, firm_id="firm_acme"):
    return await policies.create_version(
        PolicyCreateRequest(
            policy_id="wsp_trading",
            content=content,
            effective_at=effective_at,
        ),
        firm_id=firm_id,
        user_id="u",
        pool=pool,
    )


async def test_replay_consistent_when_recorded_version_in_force(ledger, policies, replay, pool):
    # v1 has been in force since well before the action
    past = datetime.now(timezone.utc) - timedelta(days=30)
    v1 = await _register(policies, pool, "Policy v1 body", effective_at=past)

    entry = await ledger.ingest(make_event("firm_acme", v1.id, v1.policy_hash), pool)
    result = await replay.replay_entry(entry["ledger_id"], "firm_acme", pool)

    assert result.status == ReplayStatus.RECONSTRUCTED_CONSISTENT
    assert result.hash_match is True
    assert result.resolved_version.id == v1.id
    assert result.policy_content == "Policy v1 body"
    assert result.effective_window.superseded_at is None


async def test_old_entry_still_reconstructs_prior_version_after_supersession(
    ledger, policies, replay, pool
):
    """The heart of 206(4)-7: an action taken under v1 must keep replaying v1
    even after v2 supersedes it."""
    past = datetime.now(timezone.utc) - timedelta(days=30)
    v1 = await _register(policies, pool, "Policy v1 body", effective_at=past)

    # Action recorded now, under v1
    entry = await ledger.ingest(make_event("firm_acme", v1.id, v1.policy_hash), pool)

    # v2 becomes effective in the future — after the action's execution time
    future = datetime.now(timezone.utc) + timedelta(days=1)
    await _register(policies, pool, "Policy v2 body", effective_at=future)

    result = await replay.replay_entry(entry["ledger_id"], "firm_acme", pool)
    assert result.status == ReplayStatus.RECONSTRUCTED_CONSISTENT
    assert result.hash_match is True
    assert result.resolved_version.id == v1.id
    assert result.policy_content == "Policy v1 body"


async def test_discrepancy_when_recorded_hash_differs_from_version_in_force(
    ledger, policies, replay, pool
):
    # v1 effective 30 days ago, v2 effective 1 hour ago (already in force now)
    v1 = await _register(
        policies, pool, "Policy v1 body", effective_at=datetime.now(timezone.utc) - timedelta(days=30)
    )
    v2 = await _register(
        policies, pool, "Policy v2 body", effective_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )

    # Entry claims it acted under v1's hash, but v2 is what was actually in force
    entry = await ledger.ingest(make_event("firm_acme", v1.id, v1.policy_hash), pool)
    result = await replay.replay_entry(entry["ledger_id"], "firm_acme", pool)

    assert result.status == ReplayStatus.RECONSTRUCTION_DISCREPANCY
    assert result.hash_match is False
    assert result.resolved_version.id == v2.id


async def test_recorded_not_in_registry(ledger, replay, pool):
    # Entry references a policy version that was never registered
    fabricated_hash = hash_payload("never-registered-policy")
    entry = await ledger.ingest(
        make_event("firm_acme", "polv_external_001", fabricated_hash), pool
    )
    result = await replay.replay_entry(entry["ledger_id"], "firm_acme", pool)

    assert result.status == ReplayStatus.RECORDED_NOT_IN_REGISTRY
    assert result.hash_match is False
    assert result.resolved_version is None
    assert result.policy_content is None
    assert result.recorded_policy_version_hash == fabricated_hash


async def test_replay_is_firm_scoped(ledger, policies, replay, pool):
    v1 = await _register(policies, pool, "Firm A policy", firm_id="firm_a")
    entry = await ledger.ingest(make_event("firm_a", v1.id, v1.policy_hash), pool)

    # A different firm cannot replay firm_a's entry
    with pytest.raises(EntryNotFoundError):
        await replay.replay_entry(entry["ledger_id"], "firm_b", pool)
