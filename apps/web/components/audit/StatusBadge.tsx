import type { EntryStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<EntryStatus, { label: string; classes: string }> = {
  AUTO_APPROVED: {
    label: "Auto-Approved",
    classes: "border-verdict-green/50 bg-verdict-green/10 text-verdict-green",
  },
  PENDING_REVIEW: {
    label: "Pending Review",
    classes: "border-verdict-amber/50 bg-verdict-amber/10 text-verdict-amber",
  },
  APPROVED: {
    label: "Approved",
    classes: "border-verdict-green/50 bg-verdict-green/10 text-verdict-green",
  },
  REJECTED: {
    label: "Rejected",
    classes: "border-verdict-red/50 bg-verdict-red/10 text-verdict-red",
  },
  ESCALATED: {
    label: "Escalated",
    classes: "border-verdict-blue/50 bg-verdict-blue/10 text-verdict-blue",
  },
};

export function StatusBadge({ status }: { status: EntryStatus }) {
  const { label, classes } = STYLES[status];
  return (
    <span
      className={cn(
        "inline-block whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-docket",
        classes,
      )}
    >
      {label}
    </span>
  );
}
