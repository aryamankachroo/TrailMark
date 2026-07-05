import { AuditLedgerTable } from "@/components/audit/AuditLedgerTable";

export default function AuditLedgerPage() {
  return (
    <div className="flex h-screen flex-col px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Audit Ledger</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          The complete, immutable record of agent activity — hash-chained, signed, and
          retained under SEC Rule 17a-4.
        </p>
      </header>
      <div className="min-h-0 flex-1">
        <AuditLedgerTable />
      </div>
    </div>
  );
}
