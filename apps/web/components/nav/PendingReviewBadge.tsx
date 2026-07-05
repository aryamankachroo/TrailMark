"use client";

import * as React from "react";

import { getQueue } from "@/lib/api-client";

/** Live count of entries awaiting supervisory attestation, shown in the nav. */
export function PendingReviewBadge() {
  const [count, setCount] = React.useState<number | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    const load = () =>
      getQueue(1, 0)
        .then((q) => !cancelled && setCount(q.total_pending))
        .catch(() => !cancelled && setCount(null));
    load();
    const interval = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!count) return null;
  return (
    <span className="ml-auto rounded-sm border border-verdict-amber/50 bg-verdict-amber/10 px-1.5 text-[10px] font-mono text-verdict-amber">
      {count}
    </span>
  );
}
