"""asyncpg connection pool.

DATABASE_URL points at the local docker-compose Postgres by default; in
production it comes from AWS Secrets Manager via the task definition.
"""

import os

import asyncpg

DEFAULT_DATABASE_URL = "postgresql://trailmark:trailmark@localhost:5432/trailmark"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
