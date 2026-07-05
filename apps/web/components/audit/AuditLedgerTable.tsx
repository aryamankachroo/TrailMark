"use client";

import * as React from "react";
import { FileText, Link2, Search } from "lucide-react";

import { listEntries } from "@/lib/api-client";
import type { EntryListResponse } from "@/lib/types";
import { abbreviateHash, formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ChainIntegrityBadge } from "./ChainIntegrityBadge";
import { EntryDetailPanel } from "./EntryDetailPanel";
import { RiskScoreBadge } from "./RiskScoreBadge";
import { StatusBadge } from "./StatusBadge";
import { ReportGeneratorPanel } from "@/components/reports/ReportGeneratorPanel";

const PAGE_SIZE = 25;

export function AuditLedgerTable() {
  const [data, setData] = React.useState<EntryListResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const [search, setSearch] = React.useState("");
  const [debouncedSearch, setDebouncedSearch] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [riskTier, setRiskTier] = React.useState("");
  const [attestation, setAttestation] = React.useState("");
  const [agentId, setAgentId] = React.useState("");
  const [offset, setOffset] = React.useState(0);

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [reportOpen, setReportOpen] = React.useState(false);

  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  React.useEffect(() => {
    setOffset(0);
  }, [debouncedSearch, dateFrom, dateTo, riskTier, attestation, agentId]);

  const refresh = React.useCallback(() => {
    setLoading(true);
    listEntries({
      action_name: debouncedSearch || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(`${dateTo}T23:59:59.999Z`).toISOString() : undefined,
      risk_tier: riskTier || undefined,
      requires_attestation:
        attestation === "" ? undefined : attestation === "required",
      agent_id: agentId || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((resp) => {
        setData(resp);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [debouncedSearch, dateFrom, dateTo, riskTier, attestation, agentId, offset]);

  React.useEffect(refresh, [refresh]);

  const agents = React.useMemo(() => {
    const set = new Set<string>();
    data?.entries.forEach((e) => set.add(e.agent_id));
    if (agentId) set.add(agentId);
    return [...set].sort();
  }, [data, agentId]);

  const pageEnd = data ? Math.min(offset + PAGE_SIZE, data.total) : 0;

  return (
    <div className="flex h-full flex-col">
      {/* Search + report generation */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2 h-4 w-4 text-ink-faint" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search the record — action name, agent, registered representative…"
            className="pl-9"
            aria-label="Search audit ledger"
          />
        </div>
        <Button onClick={() => setReportOpen(true)}>
          <FileText className="h-3.5 w-3.5" />
          Generate Report
        </Button>
      </div>

      {/* Filter row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="docket-label mr-1">Filter the record:</span>
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="w-[150px]"
          aria-label="Date from"
        />
        <span className="text-ink-faint">–</span>
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="w-[150px]"
          aria-label="Date to"
        />
        <Select value={riskTier} onChange={(e) => setRiskTier(e.target.value)} aria-label="Risk tier">
          <option value="">All Risk Tiers</option>
          <option value="LOW">Low</option>
          <option value="MEDIUM">Medium</option>
          <option value="HIGH">High</option>
          <option value="CRITICAL">Critical</option>
        </Select>
        <Select
          value={attestation}
          onChange={(e) => setAttestation(e.target.value)}
          aria-label="Attestation status"
        >
          <option value="">All Attestation Statuses</option>
          <option value="required">Attestation Required</option>
          <option value="not-required">Auto-Approved</option>
        </Select>
        <Select value={agentId} onChange={(e) => setAgentId(e.target.value)} aria-label="Agent">
          <option value="">All Agents</option>
          {agents.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </Select>
      </div>

      {/* The record */}
      <div className="panel mt-4 flex-1 overflow-x-auto">
        {error ? (
          <div className="p-8 text-center text-sm text-verdict-red">{error}</div>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-navy-600">
                {["Seq №", "Timestamp (UTC)", "Agent", "Action", "Risk Score", "Status", "Chain"].map(
                  (h) => (
                    <th key={h} className="docket-label px-4 py-2.5 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data?.entries.map((entry) => (
                <tr
                  key={entry.ledger_id}
                  onClick={() => setSelectedId(entry.ledger_id)}
                  className="cursor-pointer border-b border-navy-700/60 transition-colors hover:bg-navy-700/40"
                >
                  <td className="px-4 py-2.5 font-mono text-ink-muted">
                    {String(entry.sequence_number).padStart(6, "0")}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs">
                    {formatTimestamp(entry.timestamp_utc)}
                  </td>
                  <td className="px-4 py-2.5">
                    <div>{entry.agent_id}</div>
                    <div className="text-[11px] text-ink-faint">{entry.agent_framework}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div>{entry.action_name}</div>
                    <div className="text-[11px] text-ink-faint">{entry.action_type}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <RiskScoreBadge score={entry.risk_score} />
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={entry.status} />
                  </td>
                  <td className="px-4 py-2.5" title={entry.entry_hash}>
                    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-ink-faint">
                      <Link2 className="h-3 w-3 text-verdict-green" />
                      {abbreviateHash(entry.entry_hash, 6)}
                    </span>
                  </td>
                </tr>
              ))}
              {!loading && data && data.entries.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-sm text-ink-faint">
                    No entries of record match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer: chain attestation + pagination */}
      <div className="mt-3 flex items-center justify-between">
        {data && (
          <ChainIntegrityBadge
            verified={data.chain_integrity_verified}
            entriesChecked={data.total}
          />
        )}
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-ink-faint">
            {data ? `${data.total === 0 ? 0 : offset + 1}–${pageEnd} of ${data.total}` : "—"}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Prev
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!data || pageEnd >= data.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </div>

      <EntryDetailPanel
        ledgerId={selectedId}
        onClose={() => {
          setSelectedId(null);
          refresh(); // an attestation may have changed a status badge
        }}
      />
      <ReportGeneratorPanel open={reportOpen} onOpenChange={setReportOpen} />
    </div>
  );
}
