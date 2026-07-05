"""TrailMark API entrypoint.

Phase 2 wires in the routers (ingest, entries, attestations, replay, reports,
policies, chain). For now this exposes only a health check so the stack runs.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from db.connection import close_pool, get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="TrailMark Ledger API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
