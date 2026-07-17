import { PolicyReplayViewer } from "@/components/audit/PolicyReplayViewer";

export default function PolicyReplayPage({
  params,
}: {
  params: { ledger_id: string };
}) {
  return (
    <div className="mx-auto max-w-3xl px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Policy Replay</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Reconstruction of the exact policy version in force at the execution timestamp
          (SEC Rule 206(4)-7).
        </p>
        <p className="mt-1 font-mono text-xs text-ink-muted">{params.ledger_id}</p>
      </header>
      <PolicyReplayViewer ledgerId={params.ledger_id} />
    </div>
  );
}
