"""Policy registry service — versioned, WORM-stored firm policies.

Underpins SEC Rule 206(4)-7. Each policy version's content is:
  1. content-addressed (SHA-256 over the canonical bytes),
  2. written to WORM S3 (Object Lock COMPLIANCE, 7-year retention) — a policy
     that was in force is itself a preserved record,
  3. indexed in Postgres with an effective window.

A policy has a logical ``policy_id`` and an ordered sequence of versions. When
a new version becomes effective, the version currently in force is superseded
as of the new version's ``effective_at`` — so at any timestamp exactly one
version is in force, which is what replay resolves.
"""

import asyncio
import gzip
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from crypto.hasher import hash_payload
from models.policy import (
    PolicyCreateRequest,
    PolicySummary,
    PolicyVersionDetail,
    PolicyVersionRecord,
)
from services.ledger import generate_ulid

RETENTION_YEARS = 7


class DuplicatePolicyError(Exception):
    """The exact policy content already exists (content-addressed collision)."""


class PolicyNotFoundError(Exception):
    """No such policy version within the caller's firm."""


class PolicyService:
    def __init__(self, s3_client: Any | None = None, bucket: str | None = None):
        # boto3 honors AWS_ENDPOINT_URL — local/tests point at LocalStack.
        if s3_client is not None:
            self.s3 = s3_client
        else:
            import boto3

            self.s3 = boto3.client("s3")
        self.bucket = bucket or os.getenv("WORM_BUCKET", "trailmark-worm-dev")

    async def create_version(
        self,
        req: PolicyCreateRequest,
        firm_id: str,
        user_id: str,
        pool: asyncpg.Pool,
    ) -> PolicyVersionRecord:
        policy_hash = hash_payload(req.content)
        now = datetime.now(timezone.utc)
        effective_at = req.effective_at or now
        if effective_at.tzinfo is None:
            effective_at = effective_at.replace(tzinfo=timezone.utc)

        version_id = generate_ulid(prefix="polv_")
        retain_until = now + timedelta(days=365 * RETENTION_YEARS)
        s3_key = (
            f"policies/{firm_id}/{req.policy_id}/{version_id}.txt.gz"
        )

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Serialize version assignment + supersession per firm-policy.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    firm_id,
                    req.policy_id,
                )
                next_version = await conn.fetchval(
                    "SELECT COALESCE(MAX(version_number), 0) + 1 FROM policy_versions "
                    "WHERE firm_id = $1 AND policy_id = $2",
                    firm_id,
                    req.policy_id,
                )

                # Write content to WORM before the metadata row (same ordering
                # rationale as the ledger: never a row without its record).
                await asyncio.to_thread(
                    self.s3.put_object,
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=gzip.compress(req.content.encode("utf-8")),
                    ContentType="text/plain",
                    ContentEncoding="gzip",
                    ObjectLockMode="COMPLIANCE",
                    ObjectLockRetainUntilDate=retain_until,
                    ServerSideEncryption="aws:kms",
                )

                # Supersede the version currently in force for this policy as of
                # the new version's effective time.
                await conn.execute(
                    """
                    UPDATE policy_versions
                    SET superseded_at = $3
                    WHERE firm_id = $1 AND policy_id = $2 AND superseded_at IS NULL
                    """,
                    firm_id,
                    req.policy_id,
                    effective_at,
                )

                try:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO policy_versions (
                            id, firm_id, policy_id, name, version_number,
                            policy_hash, content_s3_key, effective_at,
                            superseded_at, created_by_user_id
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NULL,$9)
                        RETURNING *
                        """,
                        version_id, firm_id, req.policy_id, req.name, next_version,
                        policy_hash, s3_key, effective_at, user_id,
                    )
                except asyncpg.UniqueViolationError as exc:
                    # policy_hash is globally unique — identical content exists.
                    raise DuplicatePolicyError(policy_hash) from exc

        return _record_from_row(row)

    async def list_policies(self, firm_id: str, pool: asyncpg.Pool) -> list[PolicySummary]:
        """One row per logical policy — its latest version and version count."""
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (policy_id)
                   policy_id, name, id AS latest_version_id,
                   version_number AS latest_version_number,
                   policy_hash AS latest_policy_hash,
                   effective_at AS latest_effective_at,
                   COUNT(*) OVER (PARTITION BY policy_id) AS version_count,
                   MIN(effective_at) OVER (PARTITION BY policy_id) AS first_effective_at
            FROM policy_versions
            WHERE firm_id = $1
            ORDER BY policy_id, version_number DESC
            """,
            firm_id,
        )
        return [
            PolicySummary(
                policy_id=r["policy_id"],
                name=r["name"],
                latest_version_id=r["latest_version_id"],
                latest_version_number=r["latest_version_number"],
                latest_policy_hash=r["latest_policy_hash"],
                version_count=r["version_count"],
                first_effective_at=r["first_effective_at"],
                latest_effective_at=r["latest_effective_at"],
            )
            for r in rows
        ]

    async def list_versions(
        self, policy_id: str, firm_id: str, pool: asyncpg.Pool
    ) -> list[PolicyVersionRecord]:
        rows = await pool.fetch(
            "SELECT * FROM policy_versions WHERE firm_id = $1 AND policy_id = $2 "
            "ORDER BY version_number DESC",
            firm_id,
            policy_id,
        )
        return [_record_from_row(r) for r in rows]

    async def get_version(
        self, version_id: str, firm_id: str, pool: asyncpg.Pool
    ) -> PolicyVersionDetail:
        row = await pool.fetchrow(
            "SELECT * FROM policy_versions WHERE id = $1 AND firm_id = $2",
            version_id,
            firm_id,
        )
        if row is None:
            raise PolicyNotFoundError(version_id)
        content = await self._read_content(row["content_s3_key"])
        return PolicyVersionDetail(content=content, **_record_from_row(row).model_dump())

    async def resolve_in_force(
        self,
        firm_id: str,
        policy_id: str,
        at: datetime,
        pool: asyncpg.Pool,
    ) -> asyncpg.Record | None:
        """The version of ``policy_id`` in force at timestamp ``at`` — the core
        of point-in-time replay. Exactly one version satisfies the effective
        window [effective_at, superseded_at)."""
        return await pool.fetchrow(
            """
            SELECT * FROM policy_versions
            WHERE firm_id = $1 AND policy_id = $2
              AND effective_at <= $3
              AND (superseded_at IS NULL OR superseded_at > $3)
            ORDER BY version_number DESC
            LIMIT 1
            """,
            firm_id,
            policy_id,
            at,
        )

    async def find_by_id_or_hash(
        self,
        firm_id: str,
        version_id: str,
        policy_hash: str,
        pool: asyncpg.Pool,
    ) -> asyncpg.Record | None:
        """Locate the registry version an entry references, by version id first
        (exact), then by content hash (in case ids diverge across systems)."""
        return await pool.fetchrow(
            """
            SELECT * FROM policy_versions
            WHERE firm_id = $1 AND (id = $2 OR policy_hash = $3)
            ORDER BY (id = $2) DESC
            LIMIT 1
            """,
            firm_id,
            version_id,
            policy_hash,
        )

    async def _read_content(self, s3_key: str) -> str:
        obj = await asyncio.to_thread(
            self.s3.get_object, Bucket=self.bucket, Key=s3_key
        )
        return gzip.decompress(obj["Body"].read()).decode("utf-8")


def _record_from_row(row: asyncpg.Record) -> PolicyVersionRecord:
    return PolicyVersionRecord(
        id=row["id"],
        firm_id=row["firm_id"],
        policy_id=row["policy_id"],
        name=row["name"],
        version_number=row["version_number"],
        policy_hash=row["policy_hash"],
        content_s3_key=row["content_s3_key"],
        effective_at=row["effective_at"],
        superseded_at=row["superseded_at"],
        created_by_user_id=row["created_by_user_id"],
        created_at=row["created_at"],
    )
