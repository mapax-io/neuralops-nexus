import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-[10px] font-semibold transition-[filter,box-shadow,border-color,background-color,color] duration-150 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-50 cursor-pointer select-none",
  {
    variants: {
      variant: {
        primary:
          "text-accent-ink bg-accent shadow-[inset_0_1px_0_rgba(255,255,255,.15),0_10px_26px_-14px_var(--accent)] hover:brightness-105 hover:shadow-[inset_0_1px_0_rgba(255,255,255,.15),0_14px_30px_-14px_var(--accent)] active:brightness-95",
        secondary: "bg-surface text-ink border border-line hover:border-accent hover:shadow-[0_8px_20px_-14px_var(--accent-soft)] active:brightness-95",
        ghost: "text-ink2 hover:text-ink hover:bg-surface2",
        danger: "bg-crit/10 text-crit border border-crit/30 hover:bg-crit/15",
        // A text action that must read as one at rest: accent, underlined on hover, no chrome.
        link: "text-accent hover:underline underline-offset-4 decoration-accent/50 active:brightness-90",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        md: "h-10 px-4 text-sm",
        lg: "h-11 px-6 text-[15px]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  loading?: boolean;
}

export function Button({ className, variant, size, loading, disabled, children, ...props }: ButtonProps) {
  return (
    <button className={cn(button({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && (
        <span
          aria-hidden
          className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}
