"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, FileText, Plus, ScrollText } from "lucide-react";

import { getPolicyVersion, listPolicies, listPolicyVersions } from "@/lib/api-client";
import type {
  PolicySummary,
  PolicyVersionDetail,
  PolicyVersionRecord,
} from "@/lib/types";
import { abbreviateHash, formatTimestamp } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { PolicyUploadModal } from "./PolicyUploadModal";

function VersionHistory({ policyId }: { policyId: string }) {
  const [versions, setVersions] = React.useState<PolicyVersionRecord[] | null>(null);
  const [viewing, setViewing] = React.useState<PolicyVersionDetail | null>(null);

  React.useEffect(() => {
    listPolicyVersions(policyId)
      .then(setVersions)
      .catch(() => setVersions([]));
  }, [policyId]);

  function view(versionId: string) {
    getPolicyVersion(versionId)
      .then(setViewing)
      .catch(() => setViewing(null));
  }

  if (versions === null)
    return <div className="px-4 py-3 text-xs text-ink-faint">Reading version history…</div>;

  return (
    <div className="border-t border-navy-700/60 bg-navy-900/40">
      <table className="w-full text-left text-[12px]">
        <thead>
          <tr className="border-b border-navy-700/60">
            {["Version", "Policy Hash", "Effective From", "Superseded", ""].map((h) => (
              <th key={h} className="docket-label px-4 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.id} className="border-b border-navy-700/40">
              <td className="px-4 py-2 font-mono text-ink-muted">v{v.version_number}</td>
              <td className="px-4 py-2 font-mono text-ink-faint" title={v.policy_hash}>
                {abbreviateHash(v.policy_hash, 8)}
              </td>
              <td className="px-4 py-2 font-mono text-xs">{formatTimestamp(v.effective_at)}</td>
              <td className="px-4 py-2 font-mono text-xs text-ink-faint">
                {v.superseded_at ? (
                  formatTimestamp(v.superseded_at)
                ) : (
                  <span className="text-verdict-green">in force</span>
                )}
              </td>
              <td className="px-4 py-2 text-right">
                <Button variant="ghost" size="sm" onClick={() => view(v.id)}>
                  <FileText className="h-3.5 w-3.5" />
                  View
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Sheet open={viewing !== null} onOpenChange={(open) => !open && setViewing(null)}>
        <SheetContent>
          <SheetTitle className="sr-only">Policy Version Content</SheetTitle>
          <SheetDescription className="sr-only">Immutable policy text</SheetDescription>
          {viewing && (
            <div className="p-6">
              <h2 className="font-display text-lg text-gold">
                {viewing.name ?? viewing.policy_id}
              </h2>
              <p className="font-mono text-xs text-ink-muted">
                {viewing.policy_id} · v{viewing.version_number}
              </p>
              <div className="mt-3 space-y-1">
                <div className="text-[10px] uppercase tracking-docket text-ink-faint">
                  Policy Hash
                </div>
                <div className="hash-text">{viewing.policy_hash}</div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <div className="text-[10px] uppercase tracking-docket text-ink-faint">
                    Effective From
                  </div>
                  <div className="font-mono">{formatTimestamp(viewing.effective_at)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-docket text-ink-faint">
                    Superseded
                  </div>
                  <div className="font-mono">
                    {viewing.superseded_at ? formatTimestamp(viewing.superseded_at) : "—"}
                  </div>
                </div>
              </div>
              <pre className="mt-4 max-h-[70vh] overflow-auto whitespace-pre-wrap border border-navy-600 bg-navy-900/60 p-4 font-mono text-[12px] leading-relaxed text-ink-muted">
                {viewing.content}
              </pre>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

export function PolicyRegistry() {
  const [policies, setPolicies] = React.useState<PolicySummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploadPolicyId, setUploadPolicyId] = React.useState<string | undefined>();

  const refresh = React.useCallback(() => {
    listPolicies()
      .then((p) => {
        setPolicies(p);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, []);

  React.useEffect(refresh, [refresh]);

  function openUpload(policyId?: string) {
    setUploadPolicyId(policyId);
    setUploadOpen(true);
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="docket-label">
          {policies ? `${policies.length} ${policies.length === 1 ? "policy" : "policies"} of record` : "—"}
        </span>
        <Button onClick={() => openUpload()}>
          <Plus className="h-3.5 w-3.5" />
          Register Policy Version
        </Button>
      </div>

      {error ? (
        <div className="panel p-8 text-center text-sm text-verdict-red">{error}</div>
      ) : policies === null ? (
        <div className="panel p-8 text-center text-sm text-ink-faint">Reading the registry…</div>
      ) : policies.length === 0 ? (
        <div className="panel p-8 text-center">
          <ScrollText className="mx-auto h-6 w-6 text-gold-dim" />
          <p className="mt-3 text-sm text-ink-muted">
            No policies on the record yet. Register the first version to begin accruing
            replay evidence.
          </p>
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-navy-600">
                {["Policy", "Latest", "Versions", "Latest Hash", "Effective From", ""].map((h) => (
                  <th key={h} className="docket-label px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => {
                const isOpen = expanded === p.policy_id;
                return (
                  <React.Fragment key={p.policy_id}>
                    <tr
                      onClick={() => setExpanded(isOpen ? null : p.policy_id)}
                      className="cursor-pointer border-b border-navy-700/60 transition-colors hover:bg-navy-700/40"
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          {isOpen ? (
                            <ChevronDown className="h-3.5 w-3.5 text-ink-faint" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5 text-ink-faint" />
                          )}
                          <div>
                            <div>{p.name ?? p.policy_id}</div>
                            <div className="font-mono text-[11px] text-ink-faint">{p.policy_id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-ink-muted">
                        v{p.latest_version_number}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-ink-muted">{p.version_count}</td>
                      <td className="px-4 py-2.5 font-mono text-[11px] text-ink-faint" title={p.latest_policy_hash}>
                        {abbreviateHash(p.latest_policy_hash, 8)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs">
                        {formatTimestamp(p.latest_effective_at)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            openUpload(p.policy_id);
                          }}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          New Version
                        </Button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={6} className="p-0">
                          <VersionHistory policyId={p.policy_id} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <PolicyUploadModal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onCreated={refresh}
        defaultPolicyId={uploadPolicyId}
      />
    </div>
  );
}
