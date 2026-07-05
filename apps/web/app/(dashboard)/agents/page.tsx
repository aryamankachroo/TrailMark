"use client";

import * as React from "react";

import { listEntries } from "@/lib/api-client";
import type { EntrySummary } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

/** Interim registry derived from ledger activity; a first-class agent
 * registration API arrives in a later phase. */
export default function AgentsPage() {
  const [agents, setAgents] = React.useState<
    { agent_id: string; framework: string; last_action: EntrySummary }[] | null
  >(null);

  React.useEffect(() => {
    listEntries({ limit: 100 })
      .then((resp) => {
        const byAgent = new Map<string, EntrySummary>();
        for (const e of resp.entries) {
          if (!byAgent.has(e.agent_id)) byAgent.set(e.agent_id, e); // newest first
        }
        setAgents(
          [...byAgent.entries()].map(([agent_id, last_action]) => ({
            agent_id,
            framework: last_action.agent_framework,
            last_action,
          })),
        );
      })
      .catch(() => setAgents([]));
  }, []);

  return (
    <div className="px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Agent Registry</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          AI agents observed on the record, derived from recent ledger activity.
        </p>
      </header>
      {agents === null ? (
        <p className="text-sm text-ink-faint">Reading the record…</p>
      ) : agents.length === 0 ? (
        <div className="panel max-w-2xl p-8 text-center text-sm text-ink-muted">
          No agent activity on the record yet.
        </div>
      ) : (
        <div className="grid max-w-4xl grid-cols-2 gap-3">
          {agents.map((a) => (
            <div key={a.agent_id} className="panel px-4 py-3">
              <div className="text-sm text-ink">{a.agent_id}</div>
              <div className="mt-0.5 text-[11px] uppercase tracking-docket text-ink-faint">
                {a.framework}
              </div>
              <div className="mt-2 font-mono text-[11px] text-ink-muted">
                last action: {a.last_action.action_name}
              </div>
              <div className="font-mono text-[11px] text-ink-faint">
                {formatTimestamp(a.last_action.timestamp_utc)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
