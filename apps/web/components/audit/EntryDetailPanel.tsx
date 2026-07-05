"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowDown, History, ScrollText } from "lucide-react";

import { getEntry, listAttestations, verifyChain } from "@/lib/api-client";
import type { AttestationRecord, ChainVerification, FullEntry } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { ChainIntegrityBadge } from "./ChainIntegrityBadge";
import { RiskScoreBadge } from "./RiskScoreBadge";
import { StatusBadge } from "./StatusBadge";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-navy-600 px-6 py-4">
      <h3 className="docket-label mb-3">{title}</h3>
      {children}
    </section>
  );
}

function Field({ label, children, mono = false }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-docket text-ink-faint">{label}</div>
      <div className={mono ? "font-mono text-xs text-ink" : "text-sm text-ink"}>{children}</div>
    </div>
  );
}

function PayloadDisclosure({ title, payload }: { title: string; payload: unknown }) {
  if (payload == null || payload === "") return null;
  const text = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  return (
    <details className="group border border-navy-600 bg-navy-900/60">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs text-ink-muted hover:text-ink">
        {title}
      </summary>
      <pre className="max-h-64 overflow-auto border-t border-navy-600 p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
        {text}
      </pre>
    </details>
  );
}

export function EntryDetailContent({ ledgerId }: { ledgerId: string }) {
  const [entry, setEntry] = React.useState<FullEntry | null>(null);
  const [attestations, setAttestations] = React.useState<AttestationRecord[]>([]);
  const [chain, setChain] = React.useState<ChainVerification | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([getEntry(ledgerId), listAttestations(ledgerId), verifyChain()])
      .then(([e, a, c]) => {
        if (cancelled) return;
        setEntry(e);
        setAttestations(a);
        setChain(c);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [ledgerId]);

  if (error) return <div className="p-8 text-sm text-verdict-red">{error}</div>;
  if (!entry) return <div className="p-8 text-sm text-ink-faint">Retrieving immutable record…</div>;

  const latest = attestations[attestations.length - 1];
  const status = !entry.risk.requires_supervisor_review
    ? "AUTO_APPROVED"
    : latest
      ? latest.decision
      : "PENDING_REVIEW";

  return (
    <div>
      {/* Header */}
      <div className="px-6 pb-4 pt-6">
        <h2 className="font-display text-lg text-gold">Entry of Record</h2>
        <p className="font-mono text-xs text-ink-muted">{entry.ledger_id}</p>
        <div className="mt-3 flex items-center gap-3">
          <StatusBadge status={status} />
          <RiskScoreBadge score={entry.risk.risk_score} />
          <span className="rounded-sm border border-navy-600 px-1.5 py-0.5 text-[10px] uppercase tracking-docket text-ink-muted">
            {entry.risk.risk_tier}
          </span>
        </div>
      </div>

      <Section title="Record Metadata">
        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          <Field label="Sequence №" mono>{String(entry.sequence_number).padStart(6, "0")}</Field>
          <Field label="Timestamp" mono>{formatTimestamp(entry.timestamp.utc)}</Field>
          <Field label="Unix (ns)" mono>{String(entry.timestamp.unix_ns)}</Field>
          <Field label="Firm" mono>{entry.firm_id}</Field>
          <Field label="Agent">{entry.agent.agent_id} <span className="text-ink-faint">({entry.agent.framework})</span></Field>
          <Field label="Session" mono>{entry.session.session_id}</Field>
          <Field label="Registered Rep" mono>{entry.session.registered_rep_id ?? "—"}</Field>
          <Field label="Action">{entry.action.action_name} <span className="text-ink-faint">({entry.action.action_type})</span></Field>
          <Field label="Regulatory Tags" mono>{entry.regulatory_tags.join(" · ")}</Field>
          <Field label="WORM Retention" mono>
            {entry.worm_object_lock_mode} until {entry.worm_retain_until_date.slice(0, 10)}
          </Field>
        </div>
      </Section>

      <Section title="Chain of Custody">
        <div className="space-y-2">
          <Field label="Previous Entry Hash" mono>
            <span className="hash-text">{entry.previous_hash}</span>
          </Field>
          <div className="flex justify-center text-ink-faint">
            <ArrowDown className="h-3.5 w-3.5" />
          </div>
          <Field label="This Entry Hash" mono>
            <span className="hash-text text-gold-dim">{entry.entry_hash}</span>
          </Field>
          <Field label="Platform Signature (Ed25519)" mono>
            <span className="hash-text">{entry.platform_signature}</span>
          </Field>
          <div className="pt-2">
            {chain && (
              <ChainIntegrityBadge
                verified={chain.verified}
                entriesChecked={chain.entries_checked}
                brokenAtSequence={chain.broken_at_sequence}
              />
            )}
          </div>
        </div>
      </Section>

      {entry.risk.risk_flags.length > 0 && (
        <Section title="Risk Flags">
          <ul className="space-y-1">
            {entry.risk.risk_flags.map((flag) => (
              <li key={flag} className="flex items-center gap-2 text-sm text-verdict-amber">
                <span className="h-1 w-1 rounded-full bg-verdict-amber" />
                {flag}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Policy in Effect at Execution">
        <div className="grid grid-cols-1 gap-y-3">
          <Field label="Policy Version" mono>{entry.policy.policy_version_id}</Field>
          <Field label="Policy Version Hash" mono>
            <span className="hash-text">{entry.policy.policy_version_hash}</span>
          </Field>
        </div>
        <Link href={`/entry/${entry.ledger_id}/replay`}>
          <Button variant="default" size="sm" className="mt-3">
            <ScrollText className="h-3.5 w-3.5" />
            View Policy Replay
          </Button>
        </Link>
      </Section>

      <Section title="Payloads (Hashed of Record)">
        <div className="space-y-2">
          <PayloadDisclosure title="Input payload" payload={entry.input} />
          <PayloadDisclosure title="Output payload" payload={entry.output} />
          <PayloadDisclosure title="Reasoning trace" payload={entry.reasoning_trace} />
        </div>
      </Section>

      <Section title="Supervisory Attestation (FINRA 3110)">
        {attestations.length === 0 ? (
          <p className="text-sm text-ink-faint">
            {entry.risk.requires_supervisor_review
              ? "Awaiting supervisory review — this entry is in the attestation queue."
              : "No supervisory attestation required for this entry."}
          </p>
        ) : (
          <ul className="space-y-3">
            {attestations.map((a) => (
              <li key={a.id} className="border border-navy-600 bg-navy-900/50 p-3">
                <div className="flex items-center gap-2">
                  <History className="h-3.5 w-3.5 text-ink-faint" />
                  <StatusBadge status={a.decision} />
                  <span className="font-mono text-[11px] text-ink-faint">
                    {formatTimestamp(a.attested_at)}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2">
                  <Field label="Supervisor" mono>{a.supervisor_user_id}</Field>
                  <Field label="FINRA CRD" mono>{a.supervisor_finra_crd}</Field>
                  <Field label="Role">{a.supervisor_role}</Field>
                  <Field label="Reason Code" mono>{a.reason_code}</Field>
                </div>
                {a.notes && <p className="mt-2 text-sm text-ink-muted">{a.notes}</p>}
                <div className="mt-2">
                  <Field label="Attestation Signature Hash" mono>
                    <span className="hash-text">{a.signature_hash}</span>
                  </Field>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

export function EntryDetailPanel({
  ledgerId,
  onClose,
}: {
  ledgerId: string | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={ledgerId !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent>
        <SheetTitle className="sr-only">Entry of Record</SheetTitle>
        <SheetDescription className="sr-only">
          Immutable audit ledger entry detail
        </SheetDescription>
        {ledgerId && <EntryDetailContent ledgerId={ledgerId} />}
      </SheetContent>
    </Sheet>
  );
}
