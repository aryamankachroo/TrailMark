import { cn } from "@/lib/utils";

/** Risk score as a horizontal bar: green < 0.4, amber 0.4–0.75, red > 0.75. */
export function RiskScoreBadge({ score }: { score: number }) {
  const color =
    score > 0.75
      ? "bg-verdict-red"
      : score >= 0.4
        ? "bg-verdict-amber"
        : "bg-verdict-green";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-navy-600">
        <div
          className={cn("h-full rounded-full", color)}
          style={{ width: `${Math.round(Math.min(1, Math.max(0, score)) * 100)}%` }}
        />
      </div>
      <span className="font-mono text-xs text-ink-muted">{score.toFixed(3)}</span>
    </div>
  );
}
