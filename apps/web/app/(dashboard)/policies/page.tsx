import { PolicyRegistry } from "@/components/policies/PolicyRegistry";

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
      <PolicyRegistry />
    </div>
  );
}
