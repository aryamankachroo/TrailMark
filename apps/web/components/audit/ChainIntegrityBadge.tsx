import { ShieldCheck, ShieldX } from "lucide-react";

/** Reflects a REAL verification result from the ledger service — the flag it
 * renders is computed by recomputing every hash server-side, never assumed. */
export function ChainIntegrityBadge({
  verified,
  entriesChecked,
  brokenAtSequence,
}: {
  verified: boolean;
  entriesChecked?: number;
  brokenAtSequence?: number | null;
}) {
  if (verified) {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-xs text-verdict-green">
        <ShieldCheck className="h-3.5 w-3.5" />
        CHAIN INTEGRITY: ✓ VERIFIED
        {entriesChecked !== undefined && (
          <span className="text-ink-faint">({entriesChecked} entries recomputed)</span>
        )}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs text-verdict-red">
      <ShieldX className="h-3.5 w-3.5" />
      CHAIN INTEGRITY: ✗ BROKEN
      {brokenAtSequence != null && <span>AT SEQ {brokenAtSequence}</span>}
    </span>
  );
}
