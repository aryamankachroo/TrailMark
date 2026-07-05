import Link from "next/link";
import { Landmark } from "lucide-react";

import { clerkConfigured } from "@/lib/server-auth";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="panel w-full max-w-md p-8 text-center">
        <Landmark className="mx-auto h-6 w-6 text-gold" />
        <h1 className="mt-3 font-display text-xl tracking-wide text-gold">TRAILMARK</h1>
        <p className="mt-1 text-[11px] uppercase tracking-docket text-ink-faint">
          Immutable Recordkeeping for AI Agents
        </p>
        {clerkConfigured() ? (
          <ClerkSignIn />
        ) : (
          <div className="mt-6">
            <p className="text-sm text-ink-muted">
              Development mode — authentication is provided by Clerk in production
              (MFA enforced). Requests are scoped to the configured development firm.
            </p>
            <Link
              href="/"
              className="mt-4 inline-block rounded-sm border border-gold bg-gold px-6 py-2 text-xs uppercase tracking-docket text-navy-950 hover:bg-gold-bright"
            >
              Enter the Record
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

async function ClerkSignIn() {
  const { SignIn } = await import("@clerk/nextjs");
  return (
    <div className="mt-6 flex justify-center">
      <SignIn routing="hash" />
    </div>
  );
}
