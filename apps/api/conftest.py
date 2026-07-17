"""Test fixtures for the TrailMark API.

Integration tests need the local stack running:
    docker compose -f infrastructure/docker-compose.yml up -d

Tests run against a DEDICATED database (trailmark_test), created automatically
on first run, so the suite never disturbs the dev/demo data in `trailmark`
(they share one Postgres server). The Postgres schema is dropped and re-applied
per test (the audit tables are append-only — they cannot be truncated between
tests, by design). The WORM bucket is likewise a separate test bucket, reused
across runs: object-locked objects cannot be deleted, so uniqueness comes from
ULID keys, not bucket recreation.
"""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Test environment — must be set before boto3/asyncpg clients are built.
# A separate database keeps `pytest` from wiping the seeded dev/demo ledger.
os.environ.setdefault("DATABASE_URL", "postgresql://trailmark:trailmark@localhost:5432/trailmark_test")
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


def _ensure_test_database() -> None:
    """Create the dedicated test database if it is absent. Connects to the
    server's `trailmark` database (always present from the container init) to
    issue CREATE DATABASE — so the suite is self-provisioning."""
    url = urlparse(os.environ["DATABASE_URL"])
    test_db = url.path.lstrip("/")
    if test_db == "trailmark":
        return  # explicitly pointed at the dev DB; respect that, create nothing
    admin_url = urlunparse(url._replace(path="/trailmark"))

    async def _create() -> None:
        conn = await asyncpg.connect(admin_url)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", test_db
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{test_db}"')
        finally:
            await conn.close()

    asyncio.run(_create())


_ensure_test_database()

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
