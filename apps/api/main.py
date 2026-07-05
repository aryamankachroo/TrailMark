"""TrailMark API entrypoint.

Run locally (from apps/api):
    uvicorn main:app --reload

All error responses share one structured JSON shape:
    {"error": {"code": "...", "message": "...", "details": [...]}}
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from auth import enforce_production_auth_config
from db.connection import close_pool, get_pool
from routers import attestations, chain, entries, ingest, reports

logger = logging.getLogger("trailmark")


@asynccontextmanager
async def lifespan(app: FastAPI):
    enforce_production_auth_config()
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="TrailMark Ledger API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ingest.router)
app.include_router(entries.router)
app.include_router(attestations.router)
app.include_router(reports.router)
app.include_router(chain.router)


def _error_body(code: str, message: str, details: list | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        body = _error_body(
            exc.detail.get("code", "error"),
            exc.detail.get("message", ""),
            exc.detail.get("details"),
        )
    else:
        body = _error_body("error", str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(
            "validation_error",
            "Request failed validation.",
            [
                {"loc": [str(part) for part in err["loc"]], "message": err["msg"]}
                for err in exc.errors()
            ],
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "An internal error occurred."),
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
