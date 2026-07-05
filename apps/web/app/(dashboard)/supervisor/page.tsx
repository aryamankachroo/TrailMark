import { AttestationQueue } from "@/components/supervisor/AttestationQueue";

export default function SupervisorPage() {
  return (
    <div className="px-8 py-6">
      <header className="mb-5">
        <h1 className="font-display text-xl tracking-wide text-gold">Supervisory Review</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          FINRA Rule 3110 attestation queue. Every decision recorded here is permanent,
          signed, and bound to the exact ledger entry reviewed.
        </p>
      </header>
      <AttestationQueue />
    </div>
  );
}
