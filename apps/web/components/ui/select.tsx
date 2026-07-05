import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/** Styled native select — keyboard-accessible and dependency-free; the docket
 * aesthetic favors quiet form controls over animated popovers.
 * `className` sizes the wrapper (e.g. w-full, w-[180px]). */
const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <span className={cn("relative inline-flex", className)}>
    <select
      ref={ref}
      className="h-8 w-full appearance-none rounded-sm border border-navy-600 bg-navy-850 px-2 pr-7 text-sm text-ink focus-visible:outline-none focus-visible:border-gold-dim focus-visible:ring-1 focus-visible:ring-gold-dim disabled:opacity-40"
      {...props}
    >
      {children}
    </select>
    <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
  </span>
));
Select.displayName = "Select";

export { Select };
