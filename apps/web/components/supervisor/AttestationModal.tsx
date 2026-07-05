"use client";

import * as React from "react";

import { createAttestation, getReasonCodes } from "@/lib/api-client";
import type { AttestationDecision, QueueItem, ReasonCode } from "@/lib/types";
import { formatElapsed, formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { RiskScoreBadge } from "@/components/audit/RiskScoreBadge";

const DECISIONS: { value: AttestationDecision; label: string; accent: string }[] = [
  { value: "APPROVED", label: "Approve", accent: "border-verdict-green/60 data-[active=true]:bg-verdict-green/15 data-[active=true]:text-verdict-green" },
  { value: "REJECTED", label: "Reject", accent: "border-verdict-red/60 data-[active=true]:bg-verdict-red/15 data-[active=true]:text-verdict-red" },
  { value: "ESCALATED", label: "Escalate", accent: "border-verdict-blue/60 data-[active=true]:bg-verdict-blue/15 data-[active=true]:text-verdict-blue" },
];

export function AttestationModal({
  item,
  onClose,
  onAttested,
}: {
  item: QueueItem | null;
  onClose: () => void;
  onAttested: () => void;
}) {
  const [codes, setCodes] = React.useState<ReasonCode[]>([]);
  const [decision, setDecision] = React.useState<AttestationDecision>("APPROVED");
  const [reasonCode, setReasonCode] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [crd, setCrd] = React.useState("");
  const [role, setRole] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    getReasonCodes().then(setCodes).catch(() => setCodes([]));
    // Supervisor identity persists across reviews within the browser profile.
    setCrd(localStorage.getItem("trailmark.supervisor_crd") ?? "");
    setRole(localStorage.getItem("trailmark.supervisor_role") ?? "");
  }, []);

  React.useEffect(() => {
    // Reset per-entry fields when a new item is opened.
    setDecision("APPROVED");
    setReasonCode("");
    setNotes("");
    setError(null);
  }, [item?.ledger_id]);

  async function submit() {
    if (!item || !reasonCode || !crd || !role) {
      setError("Decision, reason code, FINRA CRD, and role are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createAttestation({
        audit_entry_id: item.ledger_id,
        decision,
        reason_code: reasonCode,
        notes: notes.trim() || null,
        supervisor_finra_crd: crd.trim(),
        supervisor_role: role.trim(),
      });
      localStorage.setItem("trailmark.supervisor_crd", crd.trim());
      localStorage.setItem("trailmark.supervisor_role", role.trim());
      onAttested();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Attestation failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {item && (
          <div>
            <DialogTitle>Supervisory Attestation</DialogTitle>
            <DialogDescription>
              FINRA Rule 3110 — this attestation becomes a permanent record and cannot be
              amended or withdrawn.
            </DialogDescription>

            {/* Entry under review */}
            <div className="mt-4 border border-navy-600 bg-navy-900/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink">{item.action_name}</span>
                <RiskScoreBadge score={item.risk_score} />
              </div>
              <div className="mt-1.5 grid grid-cols-2 gap-y-1 font-mono text-[11px] text-ink-muted">
                <span>{item.ledger_id}</span>
                <span>agent: {item.agent_id}</span>
                <span>{formatTimestamp(item.timestamp_utc)}</span>
                <span>rep: {item.registered_rep_id ?? "—"}</span>
              </div>
              {item.risk_flags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.risk_flags.map((f) => (
                    <span key={f} className="rounded-sm border border-verdict-amber/40 bg-verdict-amber/10 px-1.5 py-0.5 text-[10px] text-verdict-amber">
                      {f}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-2 text-[11px] text-verdict-amber">
                Pending supervisory review for {formatElapsed(item.seconds_pending)}
              </div>
            </div>

            {/* Decision */}
            <div className="mt-4">
              <div className="docket-label mb-1.5">Decision</div>
              <div className="grid grid-cols-3 gap-2">
                {DECISIONS.map(({ value, label, accent }) => (
                  <button
                    key={value}
                    type="button"
                    data-active={decision === value}
                    onClick={() => setDecision(value)}
                    className={`h-9 rounded-sm border text-xs uppercase tracking-docket text-ink-muted transition-colors ${accent}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-3">
              <div className="docket-label mb-1.5">Reason Code (FINRA 3110)</div>
              <Select
                value={reasonCode}
                onChange={(e) => setReasonCode(e.target.value)}
                className="w-full"
              >
                <option value="">Select reason code…</option>
                {codes.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="mt-3">
              <div className="docket-label mb-1.5">Notes</div>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Basis for the supervisory decision…"
              />
            </div>

            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <div className="docket-label mb-1.5">FINRA CRD №</div>
                <Input value={crd} onChange={(e) => setCrd(e.target.value)} placeholder="1234567" />
              </div>
              <div>
                <div className="docket-label mb-1.5">Supervisory Role</div>
                <Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Series 24 Principal" />
              </div>
            </div>

            {error && <p className="mt-3 text-sm text-verdict-red">{error}</p>}

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose} disabled={submitting}>
                Cancel
              </Button>
              <Button variant="primary" onClick={submit} disabled={submitting}>
                {submitting ? "Recording…" : "Record Attestation"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
