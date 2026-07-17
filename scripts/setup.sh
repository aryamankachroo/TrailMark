#!/usr/bin/env bash
# TrailMark local development bootstrap.
#
#   ./scripts/setup.sh            # bring up the stack, apply schema, seed demo data
#   ./scripts/setup.sh --reset    # additionally drop & re-apply the schema (wipes local data)
#   ./scripts/setup.sh --no-seed  # skip demo seeding
#
# Idempotent: safe to run repeatedly. Brings up the data plane (Postgres,
# Redis, LocalStack), applies the append-only schema, provisions the WORM
# bucket with S3 Object Lock, and seeds a demo firm with a hash-chained,
# signed, WORM-stored ledger plus a policy registry for 206(4)-7 replay.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infrastructure/docker-compose.yml")

FIRM="firm_demo"
ENTRIES=40
RESET=0
SEED=1
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    --no-seed) SEED=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# LocalStack S3 (boto3 honors these). Match apps/api/conftest.py defaults.
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export WORM_BUCKET="${WORM_BUCKET:-trailmark-worm-dev}"
export DATABASE_URL="${DATABASE_URL:-postgresql://trailmark:trailmark@localhost:5432/trailmark}"

API_PY="$ROOT/apps/api/.venv/bin/python"
[ -x "$API_PY" ] || API_PY="$(command -v python3)"

psql() { "${COMPOSE[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U trailmark -d trailmark "$@"; }

step() { printf '\n\033[1;33m▸ %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- data plane
step "Starting data plane (Postgres, Redis, LocalStack)…"
"${COMPOSE[@]}" up -d --wait

# ------------------------------------------------------------------- schema
if [ "$RESET" -eq 1 ]; then
  step "Resetting schema (--reset: dropping audit tables)…"
  psql <<'SQL'
DROP TABLE IF EXISTS supervisory_attestations CASCADE;
DROP TABLE IF EXISTS audit_entries CASCADE;
DROP TABLE IF EXISTS policy_versions CASCADE;
DROP FUNCTION IF EXISTS forbid_audit_mutation() CASCADE;
SQL
fi

EXISTS="$(psql -tAc "SELECT to_regclass('public.audit_entries') IS NOT NULL")"
if [ "$EXISTS" = "t" ]; then
  step "Schema already applied — skipping (use --reset to rebuild)."
else
  step "Applying PostgreSQL schema…"
  psql < "$ROOT/database/schema.sql"
fi

# --------------------------------------------------------------- WORM bucket
step "Provisioning WORM bucket ($WORM_BUCKET) with S3 Object Lock…"
"$API_PY" "$ROOT/infrastructure/aws/s3-worm-setup.py"

# --------------------------------------------------------------------- seed
if [ "$SEED" -eq 1 ]; then
  API_STARTED=0
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    step "Seeding demo data (using the API already running on :8000)…"
  else
    step "Seeding demo data (starting a temporary API on :8000)…"
    ( cd "$ROOT/apps/api" && exec "$API_PY" -m uvicorn main:app --port 8000 --log-level warning ) &
    API_PID=$!
    API_STARTED=1
    for _ in $(seq 1 50); do
      curl -sf http://localhost:8000/health >/dev/null 2>&1 && break
      sleep 0.2
    done
  fi

  "$API_PY" "$ROOT/scripts/seed_demo.py" --firm "$FIRM" --entries "$ENTRIES"

  if [ "$API_STARTED" -eq 1 ]; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
fi

# ------------------------------------------------------------------- report
cat <<EOF

$(printf '\033[1;32m✓ TrailMark local stack is ready.\033[0m')

  Data plane:   Postgres :5432 · Redis :6379 · LocalStack (S3) :4566
  WORM bucket:  arn:aws:s3:::$WORM_BUCKET (Object Lock: COMPLIANCE, 7-year retention)
  Demo firm:    $FIRM  (dev token: tmk_dev_$FIRM)

Start the services (two terminals):

  cd apps/api && uvicorn main:app --reload          # API  → http://localhost:8000
  cd apps/web && npm run dev                         # Web  → http://localhost:3000

Record one agent action from the command line:

  curl -s http://localhost:8000/v1/ingest \\
    -H 'Authorization: Bearer tmk_dev_$FIRM' \\
    -H 'Content-Type: application/json' \\
    -d '{
      "firm_id": "$FIRM",
      "agent": {"agent_id": "agent_demo", "framework": "custom"},
      "session": {"session_id": "sess_local"},
      "action": {"action_type": "tool_call", "action_name": "wire_transfer_review"},
      "policy": {"policy_version_id": "polv_ext", "policy_version_hash": "sha256:0000"},
      "input": {"amount": 250000}
    }'

Re-run demo seeding at any time:  python scripts/seed_demo.py --firm $FIRM
EOF
