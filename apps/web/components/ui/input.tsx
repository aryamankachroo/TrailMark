import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-8 w-full rounded-sm border border-navy-600 bg-navy-850 px-3 text-sm text-ink placeholder:text-ink-faint focus-visible:outline-none focus-visible:border-gold-dim focus-visible:ring-1 focus-visible:ring-gold-dim disabled:opacity-40",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
