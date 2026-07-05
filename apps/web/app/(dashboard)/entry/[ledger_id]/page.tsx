import { EntryDetailContent } from "@/components/audit/EntryDetailPanel";

/** Deep-linkable full page for a single entry of record; the same content the
 * slide-over shows from the ledger table. */
export default function EntryPage({ params }: { params: { ledger_id: string } }) {
  return (
    <div className="mx-auto max-w-3xl px-8 py-6">
      <div className="panel">
        <EntryDetailContent ledgerId={params.ledger_id} />
      </div>
    </div>
  );
}
