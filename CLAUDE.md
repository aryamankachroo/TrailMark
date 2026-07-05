# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What TrailMark is

A compliance-grade audit trail platform for AI agents in financial services. It captures
every agent action with cryptographic finality (hash-chained, Ed25519-signed, WORM-stored)
and produces regulation-formatted audit evidence for SEC Rule 17a-4, FINRA Rule 3110, and
SEC Rule 206(4)-7. The end user is a Chief Compliance Officer, General Counsel, or SEC
examiner — the UI must read like an eDiscovery tool (Relativity), not a developer dashboard.

**Terminology:** use *WORM compliance, chain of custody, supervisory attestation, immutable
recordkeeping, policy replay*. Never use "guardrails" or "drift".

## Commands

```bash
./scripts/setup.sh                      # start local stack (Postgres/Redis/LocalStack), apply schema, seed
docker compose -f infrastructure/docker-compose.yml up -d

cd apps/api
python -m pytest                        # all API tests
python -m pytest tests/test_ledger.py -k chain   # single test
uvicorn main:app --reload               # run API locally (port 8000)

cd apps/web
npm run dev                             # dashboard on port 3000
```

## Architecture

Monorepo: `apps/web` (Next.js 14 App Router + Tailwind + shadcn/ui, Clerk auth),
`apps/api` (FastAPI, async throughout, Pydantic v2, asyncpg), `packages/sdk-python`
(`trailmark-sdk`) and `packages/sdk-typescript` (`@trailmark/sdk`), `database/schema.sql`,
`infrastructure/` (Docker Compose local, ECS Fargate prod).

Data flow: agent code instrumented with an SDK → `POST /v1/ingest` → `LedgerService`
(apps/api/services/ledger.py) which (1) hashes payloads, (2) takes a per-firm advisory
lock and reads the previous entry hash, (3) computes this entry's chained hash
(apps/api/crypto/hasher.py — canonical JSON, sorted keys, compact separators),
(4) signs it with the platform Ed25519 key (apps/api/crypto/signer.py), (5) writes the
full entry to S3 with Object Lock COMPLIANCE mode + 7-year retention, (6) inserts
metadata into Postgres. Postgres holds queryable metadata; S3 WORM holds the canonical
immutable record. The hash chain is **per firm** (each firm has its own sequence and
genesis hash).

Next.js API routes are thin proxies to FastAPI — business logic lives only in `apps/api`.

## Critical constraints — never violate

1. **Append-only audit data.** Never run UPDATE or DELETE on `audit_entries` or
   `supervisory_attestations` (enforced by triggers + RLS in schema.sql — don't remove
   them). Corrections are new entries referencing the corrected entry.
2. **Signing key** lives only in AWS Secrets Manager (`trailmark/signing-key`) in
   production. Never in code, env vars, or the database. Local dev uses an ephemeral key.
3. **S3 Object Lock must be `COMPLIANCE` mode**, never `GOVERNANCE` (admins can override
   governance; compliance is legally unbreakable).
4. **Firm isolation:** every endpoint reading audit data scopes queries by the `firm_id`
   from the authenticated JWT. Never cross firms.
5. **Chain integrity badges must reflect a real verification run** — never hardcode
   "VERIFIED".
6. **Timestamps carry nanosecond precision** (`unix_ns`) — the forensic anchor.

## Build phases

Work proceeds in phases (1: ledger core → 2: API → 3: dashboard → 4: Python SDK →
5: reports → 6: dev setup). Each phase is tested before the next begins; ask the user
before moving between phases.
