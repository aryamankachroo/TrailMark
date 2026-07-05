"use client";

import * as React from "react";
import { Clock } from "lucide-react";

import { getQueue } from "@/lib/api-client";
import type { QueueItem, QueueResponse } from "@/lib/types";
import { formatElapsed, formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { RiskScoreBadge } from "@/components/audit/RiskScoreBadge";
import { AttestationModal } from "./AttestationModal";

export function AttestationQueue() {
  const [queue, setQueue] = React.useState<QueueResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [reviewing, setReviewing] = React.useState<QueueItem | null>(null);

  const refresh = React.useCallback(() => {
    getQueue(50, 0)
      .then((q) => {
        setQueue(q);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, []);

  React.useEffect(refresh, [refresh]);

  if (error) return <div className="p-8 text-sm text-verdict-red">{error}</div>;
  if (!queue) return <div className="p-8 text-sm text-ink-faint">Loading review queue…</div>;

  if (queue.total_pending === 0) {
    return (
      <div className="panel p-12 text-center">
        <p className="font-display text-lg text-verdict-green">The record is current.</p>
        <p className="mt-1 text-sm text-ink-muted">
          No agent actions await supervisory attestation.
        </p>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-sm text-ink-muted">
        <span className="font-mono text-verdict-amber">{queue.total_pending}</span> action
        {queue.total_pending === 1 ? "" : "s"} awaiting supervisory attestation — oldest first.
        Timeliness of review is itself part of the examination record.
      </p>
      <ul className="space-y-2">
        {queue.items.map((item) => (
          <li key={item.ledger_id} className="panel flex items-center gap-4 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3">
                <span className="text-sm text-ink">{item.action_name}</span>
                <span className="rounded-sm border border-navy-600 px-1.5 py-0.5 text-[10px] uppercase tracking-docket text-ink-muted">
                  {item.risk_tier}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 font-mono text-[11px] text-ink-faint">
                <span>{formatTimestamp(item.timestamp_utc)}</span>
                <span>agent: {item.agent_id}</span>
                <span>rep: {item.registered_rep_id ?? "—"}</span>
              </div>
              {item.risk_flags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {item.risk_flags.map((f) => (
                    <span
                      key={f}
                      className="rounded-sm border border-verdict-amber/40 bg-verdict-amber/10 px-1.5 py-0.5 text-[10px] text-verdict-amber"
                    >
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <RiskScoreBadge score={item.risk_score} />
            <span className="inline-flex w-24 items-center gap-1.5 font-mono text-xs text-verdict-amber">
              <Clock className="h-3.5 w-3.5" />
              {formatElapsed(item.seconds_pending)}
            </span>
            <Button size="sm" onClick={() => setReviewing(item)}>
              Review
            </Button>
          </li>
        ))}
      </ul>

      <AttestationModal
        item={reviewing}
        onClose={() => setReviewing(null)}
        onAttested={refresh}
      />
    </div>
  );
}
