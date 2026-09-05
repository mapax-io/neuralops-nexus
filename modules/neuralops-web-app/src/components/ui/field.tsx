import { cn } from "@/lib/utils";

// `required` draws the house asterisk. It is CSS-generated (::after) on
// purpose: the label's text — and so every control's accessible name — stays
// exactly the visible words. Pair it with `required` on the control itself,
// which is what assistive tech actually announces.
export function Label({ className, required, ...props }: React.LabelHTMLAttributes<HTMLLabelElement> & { required?: boolean }) {
  return (
    <label
      data-required={required || undefined}
      className={cn(
        "block text-[13px] font-medium text-ink2 mb-1.5",
        required && "after:ml-0.5 after:text-crit after:content-['*']",
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full h-10 rounded-[10px] border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink2/60",
        "outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]",
        "disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="mt-1.5 text-[12.5px] text-crit">
      {children}
    </p>
  );
}
