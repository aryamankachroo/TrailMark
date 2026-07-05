"""Authentication and firm scoping.

Every request is resolved to an AuthContext whose firm_id scopes ALL audit-data
queries (critical constraint: never return another firm's data).

Two token modes:

* Clerk JWT (production and any env with CLERK_JWKS_URL set) — RS256 JWTs
  verified against Clerk's JWKS. The firm is taken from the `firm_id` claim
  (set via Clerk session token customization) falling back to `org_id`.
* Dev API key (non-production only) — tokens of the form `tmk_dev_<firm_id>`.
  Refused outright when ENV=production; see enforce_production_auth_config().
"""

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DEV_TOKEN_PREFIX = "tmk_dev_"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    firm_id: str
    subject: str  # Clerk user id, or the dev token itself in dev mode
    token_type: str  # "clerk_jwt" | "dev_api_key"


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(os.environ["CLERK_JWKS_URL"], cache_keys=True)


def _verify_clerk_jwt(token: str) -> AuthContext:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=os.environ.get("CLERK_ISSUER"),
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise _auth_error(401, "invalid_token", f"JWT verification failed: {exc}")

    firm_id = claims.get("firm_id") or claims.get("org_id")
    if not firm_id:
        raise _auth_error(
            403, "no_firm", "Token carries no firm_id/org_id claim; cannot scope access."
        )
    return AuthContext(firm_id=firm_id, subject=claims.get("sub", ""), token_type="clerk_jwt")


def enforce_production_auth_config() -> None:
    """Called at startup: production must have Clerk configured — the dev
    token path must be unreachable."""
    if os.getenv("ENV") == "production" and not os.getenv("CLERK_JWKS_URL"):
        raise RuntimeError(
            "ENV=production requires CLERK_JWKS_URL; refusing to start with dev auth."
        )


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthContext:
    if credentials is None:
        raise _auth_error(401, "missing_token", "Authorization: Bearer token required.")
    token = credentials.credentials

    if os.getenv("CLERK_JWKS_URL"):
        return _verify_clerk_jwt(token)

    if os.getenv("ENV") != "production" and token.startswith(DEV_TOKEN_PREFIX):
        firm_id = token[len(DEV_TOKEN_PREFIX):]
        if firm_id:
            return AuthContext(firm_id=firm_id, subject=token, token_type="dev_api_key")

    raise _auth_error(401, "invalid_token", "Token not recognized.")
