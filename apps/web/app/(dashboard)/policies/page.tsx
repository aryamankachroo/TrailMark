export default function PoliciesPage() {
  return (
    <div className="px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Policy Registry</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Every version of every firm policy, content-addressed and reconstructable at
          any execution timestamp (SEC Rule 206(4)-7).
        </p>
      </header>
      <div className="panel max-w-2xl p-8 text-center">
        <p className="text-sm text-ink-muted">
          The policy registry and version-controlled policy upload arrive with the
          policy replay engine in an upcoming phase of the build.
        </p>
        <p className="mt-2 font-mono text-[11px] text-ink-faint">
          Ledger entries already record policy_version_id and policy_version_hash —
          replay evidence accrues from the first entry.
        </p>
      </div>
    </div>
  );
}
