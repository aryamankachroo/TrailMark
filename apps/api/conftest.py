"""Test fixtures for the TrailMark API.

Integration tests need the local stack running:
    docker compose -f infrastructure/docker-compose.yml up -d

Postgres schema is dropped and re-applied per test (the audit tables are
append-only — they cannot be truncated between tests, by design). The WORM
bucket is reused across runs: object-locked objects cannot be deleted, so
uniqueness comes from ULID keys, not bucket recreation.
"""

import os
from pathlib import Path

# Test environment — must be set before boto3/asyncpg clients are built.
os.environ.setdefault("DATABASE_URL", "postgresql://trailmark:trailmark@localhost:5432/trailmark")
os.environ.setdefault("WORM_BUCKET", "trailmark-worm-test")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import asyncpg
import boto3
import botocore.exceptions
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = (REPO_ROOT / "database" / "schema.sql").read_text()

DROP_ALL = """
DROP TABLE IF EXISTS supervisory_attestations CASCADE;
DROP TABLE IF EXISTS audit_entries CASCADE;
DROP TABLE IF EXISTS policy_versions CASCADE;
DROP FUNCTION IF EXISTS forbid_audit_mutation() CASCADE;
"""


@pytest.fixture
async def pool():
    """Fresh schema per test, applied to the local docker-compose Postgres."""
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(DROP_ALL)
        await conn.execute(SCHEMA_SQL)
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
def worm_bucket():
    """Ensure the LocalStack WORM bucket exists, Object Lock enabled."""
    s3 = boto3.client("s3")
    bucket = os.environ["WORM_BUCKET"]
    try:
        s3.create_bucket(Bucket=bucket, ObjectLockEnabledForBucket=True)
    except botocore.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    return bucket
