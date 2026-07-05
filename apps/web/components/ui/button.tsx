import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm text-xs font-medium uppercase tracking-docket transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default:
          "border border-gold-dim bg-navy-700 text-gold hover:bg-navy-600 hover:text-gold-bright",
        primary: "border border-gold bg-gold text-navy-950 hover:bg-gold-bright",
        ghost: "text-ink-muted hover:bg-navy-700 hover:text-ink",
        outline: "border border-navy-600 text-ink-muted hover:border-navy-500 hover:text-ink",
        destructive: "border border-verdict-red/60 text-verdict-red hover:bg-verdict-red/10",
      },
      size: {
        default: "h-8 px-4 py-1",
        sm: "h-7 px-3",
        lg: "h-10 px-6",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
