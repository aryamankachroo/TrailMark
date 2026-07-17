-- =============================================================================
-- TrailMark — PostgreSQL schema
--
-- audit_entries and supervisory_attestations are APPEND-ONLY (SEC Rule 17a-4).
-- No UPDATE or DELETE ever runs against them. This is enforced three ways:
--   1. BEFORE UPDATE/DELETE/TRUNCATE triggers that raise an exception (loud failure)
--   2. Row-level security FORCEd on, with only SELECT and INSERT policies
--   3. Application discipline: corrections are new entries referencing the
--      corrected entry, never mutations
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Immutability guard: any UPDATE/DELETE/TRUNCATE on an audit table is an error.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION forbid_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'IMMUTABLE RECORDKEEPING VIOLATION: % on % is forbidden (SEC 17a-4). '
        'Corrections must be appended as new entries referencing the original.',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'raise_exception';
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- audit_entries — one row per agent action, hash-chained per firm.
--
-- The chain is PER FIRM: each firm has its own sequence starting at 1 and its
-- own genesis previous_hash (sha256:000...0), so sequence_number is unique per
-- firm rather than globally.
-- -----------------------------------------------------------------------------
CREATE TABLE audit_entries (
    id                    BIGSERIAL PRIMARY KEY,
    ledger_id             TEXT NOT NULL UNIQUE,       -- ULID format: entry_01J4K...
    sequence_number       BIGINT NOT NULL,
    previous_hash         TEXT NOT NULL,
    entry_hash            TEXT NOT NULL UNIQUE,
    platform_signature    TEXT NOT NULL,
    timestamp_utc         TIMESTAMPTZ NOT NULL,
    unix_ns               BIGINT NOT NULL,
    firm_id               TEXT NOT NULL,
    agent_id              TEXT NOT NULL,
    agent_framework       TEXT NOT NULL,
    session_id            TEXT NOT NULL,
    registered_rep_id     TEXT,
    action_type           TEXT NOT NULL,
    action_name           TEXT NOT NULL,
    input_payload_hash    TEXT NOT NULL,
    output_payload_hash   TEXT NOT NULL,
    reasoning_trace_hash  TEXT,
    risk_score            NUMERIC(4,3) NOT NULL DEFAULT 0,
    risk_tier             TEXT NOT NULL DEFAULT 'LOW'
                          CHECK (risk_tier IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    risk_flags            JSONB NOT NULL DEFAULT '[]',
    requires_attestation  BOOLEAN NOT NULL DEFAULT FALSE,
    policy_version_id     TEXT NOT NULL,
    policy_version_hash   TEXT NOT NULL,
    worm_s3_key           TEXT NOT NULL,
    worm_retain_until     TIMESTAMPTZ NOT NULL,
    regulatory_tags       TEXT[] NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (firm_id, sequence_number)
);

CREATE TRIGGER audit_entries_immutable_row
    BEFORE UPDATE OR DELETE ON audit_entries
    FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation();

CREATE TRIGGER audit_entries_immutable_truncate
    BEFORE TRUNCATE ON audit_entries
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_mutation();

ALTER TABLE audit_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_entries_select ON audit_entries FOR SELECT USING (TRUE);
CREATE POLICY audit_entries_insert ON audit_entries FOR INSERT WITH CHECK (TRUE);
-- No UPDATE/DELETE policies: mutations are denied even if the triggers are dropped.

-- -----------------------------------------------------------------------------
-- policy_versions — every version of every firm policy, content WORM-stored.
--
-- Underpins SEC Rule 206(4)-7 policy replay: an examiner must be able to
-- reconstruct the exact policy text in force at an action's execution
-- timestamp. Each version carries an effective window [effective_at,
-- superseded_at); superseded_at is set (once) when a newer version becomes
-- effective. Policy content itself is immutable per version (new content =
-- new version row) and is content-addressed by policy_hash.
--
-- firm_id scopes the registry per firm (critical constraint: never cross
-- firms). policy_hash is globally unique — identical content re-uploaded is a
-- conflict, not a silent duplicate.
-- -----------------------------------------------------------------------------
CREATE TABLE policy_versions (
    id                    TEXT PRIMARY KEY,
    firm_id               TEXT NOT NULL,
    policy_id             TEXT NOT NULL,
    name                  TEXT,
    version_number        INTEGER NOT NULL,
    policy_hash           TEXT NOT NULL UNIQUE,
    content_s3_key        TEXT NOT NULL,
    effective_at          TIMESTAMPTZ NOT NULL,
    superseded_at         TIMESTAMPTZ,
    created_by_user_id    TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(firm_id, policy_id, version_number)
);

-- Point-in-time replay resolution: "which version of this policy was in force
-- at timestamp T?" scans a firm's policy by effective window.
CREATE INDEX idx_policy_versions_replay
    ON policy_versions(firm_id, policy_id, effective_at DESC);
CREATE INDEX idx_policy_versions_hash ON policy_versions(policy_hash);

-- -----------------------------------------------------------------------------
-- supervisory_attestations — FINRA Rule 3110 supervisory review records.
-- Append-only: an attestation, once made, is a permanent regulatory record.
-- -----------------------------------------------------------------------------
CREATE TABLE supervisory_attestations (
    id                    TEXT PRIMARY KEY,
    audit_entry_id        TEXT NOT NULL REFERENCES audit_entries(ledger_id),
    supervisor_user_id    TEXT NOT NULL,
    supervisor_finra_crd  TEXT NOT NULL,
    supervisor_role       TEXT NOT NULL,
    decision              TEXT NOT NULL CHECK (decision IN ('APPROVED','REJECTED','ESCALATED')),
    reason_code           TEXT NOT NULL,
    notes                 TEXT,
    signature_hash        TEXT NOT NULL,
    attested_at           TIMESTAMPTZ NOT NULL,
    ip_address            INET NOT NULL,
    user_agent            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER supervisory_attestations_immutable_row
    BEFORE UPDATE OR DELETE ON supervisory_attestations
    FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation();

CREATE TRIGGER supervisory_attestations_immutable_truncate
    BEFORE TRUNCATE ON supervisory_attestations
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_mutation();

ALTER TABLE supervisory_attestations ENABLE ROW LEVEL SECURITY;
ALTER TABLE supervisory_attestations FORCE ROW LEVEL SECURITY;
CREATE POLICY supervisory_attestations_select ON supervisory_attestations FOR SELECT USING (TRUE);
CREATE POLICY supervisory_attestations_insert ON supervisory_attestations FOR INSERT WITH CHECK (TRUE);

-- -----------------------------------------------------------------------------
-- Indexes for dashboard search performance
-- -----------------------------------------------------------------------------
CREATE INDEX idx_audit_entries_firm_timestamp ON audit_entries(firm_id, timestamp_utc DESC);
CREATE INDEX idx_audit_entries_agent ON audit_entries(agent_id, timestamp_utc DESC);
CREATE INDEX idx_audit_entries_risk ON audit_entries(risk_tier, requires_attestation);
CREATE INDEX idx_attestations_entry ON supervisory_attestations(audit_entry_id);
