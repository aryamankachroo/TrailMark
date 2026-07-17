/** Mirrors of the FastAPI response models (apps/api). */

export type RiskTier = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type EntryStatus =
  | "AUTO_APPROVED"
  | "PENDING_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "ESCALATED";

export interface EntrySummary {
  ledger_id: string;
  sequence_number: number;
  timestamp_utc: string;
  agent_id: string;
  agent_framework: string;
  registered_rep_id: string | null;
  action_type: string;
  action_name: string;
  risk_score: number;
  risk_tier: RiskTier;
  requires_attestation: boolean;
  status: EntryStatus;
  entry_hash: string;
}

export interface EntryListResponse {
  entries: EntrySummary[];
  total: number;
  limit: number;
  offset: number;
  chain_integrity_verified: boolean;
}

/** Full immutable record as stored in WORM S3. */
export interface FullEntry {
  "@context": string;
  "@type": string;
  ledger_id: string;
  sequence_number: number;
  previous_hash: string;
  entry_hash: string;
  platform_signature: string;
  timestamp: { utc: string; unix_ns: number };
  firm_id: string;
  agent: { agent_id: string; framework: string; agent_version: string | null };
  session: { session_id: string; registered_rep_id: string | null };
  action: { action_type: string; action_name: string };
  policy: { policy_version_id: string; policy_version_hash: string };
  risk: {
    risk_score: number;
    risk_tier: RiskTier;
    risk_flags: string[];
    requires_supervisor_review: boolean;
  };
  input: unknown;
  output: unknown;
  reasoning_trace: string | null;
  input_payload_hash: string;
  output_payload_hash: string;
  reasoning_trace_hash: string | null;
  regulatory_tags: string[];
  worm_s3_key: string;
  worm_retain_until_date: string;
  worm_object_lock_mode: string;
}

export interface ChainVerification {
  firm_id: string;
  verified: boolean;
  entries_checked: number;
  broken_at_sequence: number | null;
}

export type AttestationDecision = "APPROVED" | "REJECTED" | "ESCALATED";

export interface AttestationRecord {
  id: string;
  audit_entry_id: string;
  supervisor_user_id: string;
  supervisor_finra_crd: string;
  supervisor_role: string;
  decision: AttestationDecision;
  reason_code: string;
  notes: string | null;
  signature_hash: string;
  attested_at: string;
  ip_address: string;
  user_agent: string | null;
}

export interface ReasonCode {
  code: string;
  label: string;
}

export interface QueueItem {
  ledger_id: string;
  sequence_number: number;
  timestamp_utc: string;
  seconds_pending: number;
  agent_id: string;
  registered_rep_id: string | null;
  action_type: string;
  action_name: string;
  risk_score: number;
  risk_tier: RiskTier;
  risk_flags: string[];
}

export interface QueueResponse {
  items: QueueItem[];
  total_pending: number;
  limit: number;
  offset: number;
}

/** Policy registry + SEC 206(4)-7 replay (mirrors apps/api/models/policy.py). */

export interface PolicyVersionRecord {
  id: string;
  firm_id: string;
  policy_id: string;
  name: string | null;
  version_number: number;
  policy_hash: string;
  content_s3_key: string;
  effective_at: string;
  superseded_at: string | null;
  created_by_user_id: string;
  created_at: string;
}

export interface PolicyVersionDetail extends PolicyVersionRecord {
  content: string;
}

export interface PolicySummary {
  policy_id: string;
  name: string | null;
  latest_version_id: string;
  latest_version_number: number;
  latest_policy_hash: string;
  version_count: number;
  first_effective_at: string;
  latest_effective_at: string;
}

export type ReplayStatus =
  | "RECONSTRUCTED_CONSISTENT"
  | "RECONSTRUCTION_DISCREPANCY"
  | "RECORDED_NOT_IN_REGISTRY";

export interface EffectiveWindow {
  effective_at: string;
  superseded_at: string | null;
}

export interface ReplayResolution {
  ledger_id: string;
  execution_timestamp_utc: string;
  execution_unix_ns: number;
  recorded_policy_version_id: string;
  recorded_policy_version_hash: string;
  status: ReplayStatus;
  hash_match: boolean;
  resolved_version: PolicyVersionRecord | null;
  effective_window: EffectiveWindow | null;
  policy_content: string | null;
}
