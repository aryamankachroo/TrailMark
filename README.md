# TrailMark

Compliance-grade audit trail platform for AI agents in financial services.

TrailMark sits between AI agents and their execution environments. It captures every
agent action with cryptographic finality and produces regulation-formatted audit
evidence on demand, satisfying three statutory mandates:

1. **SEC Rule 17a-4** — WORM-compliant immutable storage (non-rewriteable, non-erasable)
2. **FINRA Rule 3110** — Supervisory attestation stamps on every high-risk decision
3. **SEC Rule 206(4)-7** — Policy version reconstruction at exact execution timestamp

## Monorepo layout

| Path | What it is |
| --- | --- |
| `apps/api` | FastAPI backend — ingest, ledger, attestations, replay, reports |
| `apps/web` | Next.js 14 eDiscovery-style dashboard |
| `packages/sdk-python` | `trailmark-sdk` — Python instrumentation SDK |
| `packages/sdk-typescript` | `@trailmark/sdk` — TypeScript instrumentation SDK |
| `infrastructure` | Docker Compose (local) + AWS (ECS Fargate, S3 Object Lock) |
| `database` | PostgreSQL schema (append-only audit tables) |

## Local development

```bash
./scripts/setup.sh   # starts Postgres, Redis, LocalStack; applies schema; seeds a test firm
```

- API: http://localhost:8000
- Web: http://localhost:3000

## Running tests

```bash
cd apps/api
python -m pytest            # unit + integration (integration needs docker compose up)
```

Tests run against a dedicated `trailmark_test` database (created automatically),
so they never disturb the seeded dev/demo data in `trailmark`.
