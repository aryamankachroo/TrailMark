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
