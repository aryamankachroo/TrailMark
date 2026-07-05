import Link from "next/link";
import { ScrollText } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function PolicyReplayPage({
  params,
}: {
  params: { ledger_id: string };
}) {
  return (
    <div className="mx-auto max-w-3xl px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Policy Replay</h1>
        <p className="mt-0.5 font-mono text-xs text-ink-muted">{params.ledger_id}</p>
      </header>
      <div className="panel p-8 text-center">
        <ScrollText className="mx-auto h-6 w-6 text-gold-dim" />
        <p className="mt-3 text-sm text-ink-muted">
          Policy replay — reconstruction of the exact policy version in force at the
          execution timestamp (SEC Rule 206(4)-7) — ships with the replay engine in an
          upcoming phase of the build.
        </p>
        <p className="mt-2 font-mono text-[11px] text-ink-faint">
          This entry&apos;s policy_version_hash is already on the record; replay will
          resolve it against the policy registry.
        </p>
        <Link href={`/entry/${params.ledger_id}`}>
          <Button variant="outline" className="mt-5">
            Back to Entry of Record
          </Button>
        </Link>
      </div>
    </div>
  );
}
