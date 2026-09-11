import { Check, Minus } from "lucide-react";
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

// Browser and password-manager autofill is for the login page only; every
// other field is app data (model ids, API keys, names). Chrome ignores
// autocomplete="off" on password fields and offers saved logins to them, so a
// secret gets "new-password" (honoured) plus the manager opt-outs. A field
// that passes a credential hint (email, current-password, new-password…)
// keeps autofill — that is how login, reset and change-password opt in.
const MANAGER_OPT_OUT = { "data-1p-ignore": "", "data-lpignore": "true", "data-bwignore": "true", "data-form-type": "other" } as const;

export function Input({ className, autoComplete, type, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  const credential = autoComplete !== undefined && autoComplete !== "off";
  const resolved = credential ? autoComplete : type === "password" ? "new-password" : "off";
  return (
    <input
      type={type}
      autoComplete={resolved}
      {...(credential ? {} : MANAGER_OPT_OUT)}
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

// Themed tri-state checkbox (button + aria-checked) — native color styling is
// unreliable across the token themes, so we draw it.
export function Checkbox({ checked, indeterminate, onToggle, label, disabled }: {
  checked: boolean;
  indeterminate?: boolean;
  onToggle: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "flex size-[18px] flex-none items-center justify-center rounded-[5px] border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        checked || indeterminate ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface hover:border-ink2",
      )}
    >
      {indeterminate ? <Minus size={12} strokeWidth={3} /> : checked ? <Check size={12} strokeWidth={3} /> : null}
    </button>
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
