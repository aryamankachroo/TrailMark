"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileWarning, ScrollText, ShieldAlert } from "lucide-react";

import { getReplay } from "@/lib/api-client";
import type { ReplayResolution, ReplayStatus } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const STATUS_META: Record<
  ReplayStatus,
  { label: string; blurb: string; tone: string; Icon: typeof CheckCircle2 }
> = {
  RECONSTRUCTED_CONSISTENT: {
    label: "Reconstructed — Consistent",
    blurb:
      "The policy version in force at the execution timestamp was reconstructed from the registry, and its content hash matches the hash recorded on this entry. The record is corroborated end to end.",
    tone: "text-verdict-green border-verdict-green/50 bg-verdict-green/10",
    Icon: CheckCircle2,
  },
  RECONSTRUCTION_DISCREPANCY: {
    label: "Reconstruction Discrepancy",
    blurb:
      "The policy version reconstructed for the execution timestamp does not match the hash this entry recorded. This condition requires escalation.",
    tone: "text-verdict-red border-verdict-red/50 bg-verdict-red/10",
    Icon: ShieldAlert,
  },
  RECORDED_NOT_IN_REGISTRY: {
    label: "Not in Policy Registry",
    blurb:
      "The policy version this entry references is not present in the registry, so the policy text cannot be reconstructed. The recorded policy hash remains on the immutable record.",
    tone: "text-verdict-amber border-verdict-amber/50 bg-verdict-amber/10",
    Icon: FileWarning,
  },
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-docket text-ink-faint">{label}</div>
      <div className="font-mono text-xs text-ink">{children}</div>
    </div>
  );
}

export function PolicyReplayViewer({ ledgerId }: { ledgerId: string }) {
  const [replay, setReplay] = React.useState<ReplayResolution | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getReplay(ledgerId)
      .then((r) => !cancelled && setReplay(r))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [ledgerId]);

  if (error) return <div className="panel p-8 text-sm text-verdict-red">{error}</div>;
  if (!replay)
    return <div className="panel p-8 text-sm text-ink-faint">Reconstructing policy in force…</div>;

  const meta = STATUS_META[replay.status];
  const { Icon } = meta;

  return (
    <div className="space-y-4">
      {/* Verdict */}
      <div className={`panel border p-4 ${meta.tone}`}>
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4" />
          <span className="text-sm font-medium uppercase tracking-docket">{meta.label}</span>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">{meta.blurb}</p>
      </div>

      {/* Reconstruction evidence */}
      <div className="panel p-4">
        <h3 className="docket-label mb-3">Reconstruction Evidence</h3>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          <Field label="Execution Timestamp">
            {formatTimestamp(replay.execution_timestamp_utc)}
          </Field>
          <Field label="Execution Unix (ns)">{String(replay.execution_unix_ns)}</Field>
          <Field label="Recorded Policy Version">{replay.recorded_policy_version_id}</Field>
          <Field label="Hash Cross-Check">
            <span className={replay.hash_match ? "text-verdict-green" : "text-verdict-red"}>
              {replay.hash_match ? "MATCH" : "NO MATCH"}
            </span>
          </Field>
          <div className="col-span-2">
            <Field label="Recorded Policy Hash (at execution)">
              <span className="hash-text">{replay.recorded_policy_version_hash}</span>
            </Field>
          </div>
          {replay.resolved_version && (
            <div className="col-span-2">
              <Field label="Reconstructed Version Hash (in force)">
                <span
                  className={`hash-text ${replay.hash_match ? "text-verdict-green" : "text-verdict-red"}`}
                >
                  {replay.resolved_version.policy_hash}
                </span>
              </Field>
            </div>
          )}
        </div>

        {replay.resolved_version && replay.effective_window && (
          <div className="mt-4 border-t border-navy-600 pt-3">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              <Field label="Policy">
                {replay.resolved_version.name ?? replay.resolved_version.policy_id}
                <span className="text-ink-faint"> · v{replay.resolved_version.version_number}</span>
              </Field>
              <Field label="Version ID">{replay.resolved_version.id}</Field>
              <Field label="Effective From">
                {formatTimestamp(replay.effective_window.effective_at)}
              </Field>
              <Field label="Superseded">
                {replay.effective_window.superseded_at
                  ? formatTimestamp(replay.effective_window.superseded_at)
                  : "— still in force"}
              </Field>
            </div>
          </div>
        )}
      </div>

      {/* Policy text as it stood at execution */}
      {replay.policy_content != null && (
        <div className="panel p-4">
          <h3 className="docket-label mb-3">Policy Text In Force at Execution</h3>
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap border border-navy-600 bg-navy-900/60 p-4 font-mono text-[12px] leading-relaxed text-ink-muted">
            {replay.policy_content}
          </pre>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Link href={`/entry/${replay.ledger_id}`}>
          <Button variant="outline" size="sm">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Entry of Record
          </Button>
        </Link>
        <Link href="/policies">
          <Button variant="ghost" size="sm">
            <ScrollText className="h-3.5 w-3.5" />
            Policy Registry
          </Button>
        </Link>
      </div>
    </div>
  );
}
