/** Browser-side client. All calls go through the Next.js proxy at /api/v1/*,
 * which attaches the firm-scoped bearer token server-side — the browser never
 * holds an API credential. */

import type {
  AttestationDecision,
  AttestationRecord,
  ChainVerification,
  EntryListResponse,
  FullEntry,
  QueueResponse,
  ReasonCode,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!resp.ok) {
    let code = "error";
    let message = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, code, message);
  }
  return resp.json();
}

export interface EntryFilters {
  date_from?: string;
  date_to?: string;
  agent_id?: string;
  risk_tier?: string;
  requires_attestation?: boolean;
  action_name?: string;
  limit?: number;
  offset?: number;
}

export function listEntries(filters: EntryFilters): Promise<EntryListResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return api(`/v1/entries?${params}`);
}

export function getEntry(ledgerId: string): Promise<FullEntry> {
  return api(`/v1/entries/${encodeURIComponent(ledgerId)}`);
}

export function verifyChain(): Promise<ChainVerification> {
  return api("/v1/chain/verify");
}

export function getQueue(limit = 50, offset = 0): Promise<QueueResponse> {
  return api(`/v1/attestations/queue?limit=${limit}&offset=${offset}`);
}

export function getReasonCodes(): Promise<ReasonCode[]> {
  return api("/v1/attestations/reason-codes");
}

export function listAttestations(ledgerId: string): Promise<AttestationRecord[]> {
  return api(`/v1/attestations?audit_entry_id=${encodeURIComponent(ledgerId)}`);
}

export function createAttestation(body: {
  audit_entry_id: string;
  decision: AttestationDecision;
  reason_code: string;
  notes: string | null;
  supervisor_finra_crd: string;
  supervisor_role: string;
}): Promise<AttestationRecord> {
  return api("/v1/attestations", { method: "POST", body: JSON.stringify(body) });
}
