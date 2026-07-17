"""Policy registry integration tests (SEC 206(4)-7 foundation).

Requires the local stack (Postgres + LocalStack S3):
    docker compose -f infrastructure/docker-compose.yml up -d
"""

from datetime import datetime, timedelta, timezone

import boto3
import pytest

from crypto.hasher import hash_payload
from models.policy import PolicyCreateRequest
from services.policy import (
    DuplicatePolicyError,
    PolicyNotFoundError,
    PolicyService,
)


@pytest.fixture
def policies(worm_bucket):
    return PolicyService(bucket=worm_bucket)


def make_request(policy_id="wsp_trade_surveillance", content="Policy text v1", **kw):
    return PolicyCreateRequest(policy_id=policy_id, content=content, **kw)


async def test_create_version_is_content_addressed_and_worm_stored(policies, pool, worm_bucket):
    rec = await policies.create_version(
        make_request(content="Do not front-run client orders.", name="Trade Surveillance"),
        firm_id="firm_acme",
        user_id="user_1",
        pool=pool,
    )

    assert rec.version_number == 1
    assert rec.superseded_at is None
    assert rec.policy_hash == hash_payload("Do not front-run client orders.")

    # content reads back verbatim from WORM, and the S3 object is COMPLIANCE-locked
    detail = await policies.get_version(rec.id, "firm_acme", pool)
    assert detail.content == "Do not front-run client orders."

    s3 = boto3.client("s3")
    head = s3.head_object(Bucket=worm_bucket, Key=rec.content_s3_key)
    assert head["ObjectLockMode"] == "COMPLIANCE"


async def test_new_version_supersedes_prior(policies, pool):
    v1 = await policies.create_version(
        make_request(content="v1 text"), firm_id="firm_acme", user_id="u", pool=pool
    )
    v2 = await policies.create_version(
        make_request(content="v2 text"), firm_id="firm_acme", user_id="u", pool=pool
    )

    assert v2.version_number == 2
    assert v2.superseded_at is None

    # v1 is now superseded exactly as of v2's effective time
    versions = await policies.list_versions("wsp_trade_surveillance", "firm_acme", pool)
    v1_now = next(v for v in versions if v.version_number == 1)
    assert v1_now.superseded_at == v2.effective_at

    summaries = await policies.list_policies("firm_acme", pool)
    assert len(summaries) == 1
    assert summaries[0].version_count == 2
    assert summaries[0].latest_version_number == 2


async def test_duplicate_content_rejected(policies, pool):
    await policies.create_version(
        make_request(content="identical"), firm_id="firm_acme", user_id="u", pool=pool
    )
    with pytest.raises(DuplicatePolicyError):
        await policies.create_version(
            make_request(content="identical"), firm_id="firm_acme", user_id="u", pool=pool
        )


async def test_backdated_effective_at_is_honored(policies, pool):
    backdated = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rec = await policies.create_version(
        make_request(content="backdated", effective_at=backdated),
        firm_id="firm_acme",
        user_id="u",
        pool=pool,
    )
    assert rec.effective_at == backdated


async def test_firm_scoping(policies, pool):
    rec = await policies.create_version(
        make_request(content="firm a policy"), firm_id="firm_a", user_id="u", pool=pool
    )

    # firm_b cannot see firm_a's registry or read its version
    assert await policies.list_policies("firm_b", pool) == []
    with pytest.raises(PolicyNotFoundError):
        await policies.get_version(rec.id, "firm_b", pool)


async def test_same_content_allowed_across_firms_is_actually_a_conflict(policies, pool):
    """policy_hash is globally unique — identical content in a second firm still
    collides. Documented behavior: content is content-addressed platform-wide."""
    await policies.create_version(
        make_request(content="shared text"), firm_id="firm_a", user_id="u", pool=pool
    )
    with pytest.raises(DuplicatePolicyError):
        await policies.create_version(
            make_request(content="shared text"), firm_id="firm_b", user_id="u", pool=pool
        )
