import Link from "next/link";
import {
  BookMarked,
  FileCheck2,
  FileText,
  Landmark,
  ScrollText,
  Bot,
} from "lucide-react";

import { PendingReviewBadge } from "@/components/nav/PendingReviewBadge";

const NAV = [
  { href: "/", label: "Audit Ledger", icon: BookMarked },
  { href: "/supervisor", label: "Supervisory Review", icon: FileCheck2, badge: true },
  { href: "/reports", label: "Examination Reports", icon: FileText },
  { href: "/policies", label: "Policy Registry", icon: ScrollText },
  { href: "/agents", label: "Agent Registry", icon: Bot },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-60 flex-col border-r border-navy-600 bg-navy-850">
        <div className="border-b border-navy-600 px-5 py-5">
          <div className="flex items-center gap-2.5">
            <Landmark className="h-5 w-5 text-gold" />
            <div>
              <div className="font-display text-base tracking-wide text-gold">
                TRAILMARK
              </div>
              <div className="text-[10px] uppercase tracking-docket text-ink-faint">
                Immutable Recordkeeping
              </div>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3 py-4">
          {NAV.map(({ href, label, icon: Icon, badge }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] text-ink-muted transition-colors hover:bg-navy-700 hover:text-ink"
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
              {badge && <PendingReviewBadge />}
            </Link>
          ))}
        </nav>
        <div className="border-t border-navy-600 px-5 py-4">
          <div className="docket-label">Retention Mandate</div>
          <div className="mt-1 font-mono text-[11px] text-ink-faint">
            SEC 17a-4 · WORM · 7 YEARS
          </div>
        </div>
      </aside>
      <main className="ml-60 flex-1">{children}</main>
    </div>
  );
}
