"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, CircleAlert, Trash2, TriangleAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Modal: animated overlay + panel, Escape/backdrop close, focus moves in on
// open, body scroll locked while open.
//
// Anatomy: header and footer are PINNED; only the body between them scrolls
// (capped at 85vh). Form dialogs keep their <form> in the body and associate
// footer submit buttons via the `form` attribute — Enter-to-submit still works.
// Stack of open dialogs (module-level): slash-command dialogs can host
// tabs whose own create/edit dialogs open ON TOP. Escape must close only
// the topmost layer, never the whole stack in one press.
const openDialogStack: symbol[] = [];

// One width for every form dialog (4xl) so sectioned forms get room for
// two-column rows; only confirmations stay narrow — a one-line question
// stretched to 4xl reads wrong.
const DIALOG_SIZES = {
  sm: "max-w-md",    // confirmations
  md: "max-w-4xl",
  lg: "max-w-4xl",
  xl: "max-w-4xl",
  "2xl": "max-w-4xl",
} as const;

export type DialogSize = keyof typeof DIALOG_SIZES;

// The icon chip's colour says what kind of dialog this is before the title
// is read: accent = create/add, info = edit/view/people, warn = a cautious
// confirm (sign out, end session), crit = destructive, ok = success/connect.
const DIALOG_TONES = {
  neutral: "border-line bg-surface2 text-ink2",
  accent: "border-accent/30 bg-accent/12 text-accent",
  info: "border-info/30 bg-info/12 text-info",
  ok: "border-ok/30 bg-ok/12 text-ok",
  warn: "border-warn/35 bg-warn/12 text-warn",
  crit: "border-crit/30 bg-crit/12 text-crit",
} as const;

export type DialogTone = keyof typeof DIALOG_TONES;

// Scrollable middle. Hairlines only appear when the content actually
// overflows — short dialogs keep the clean undivided look.
function DialogBody({ children, hasFooter }: { children: React.ReactNode; hasFooter: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setOverflowing(el.scrollHeight > el.clientHeight + 1);
    check();
    if (typeof ResizeObserver === "undefined") return; // jsdom — the mount check above still ran
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className={cn(
        "min-h-0 flex-1 overflow-y-auto border-y border-transparent px-6",
        hasFooter ? "pb-1" : "pb-6",
        overflowing && "border-line",
      )}
    >
      {children}
    </div>
  );
}

export function Dialog({ open, onClose, title, description, icon, tone = "neutral", children, footer, className, size = "md" }: {
  open: boolean;
  onClose: () => void;
  title: string;
  // Rendered as the first paragraph of the scrolling body (and announced as
  // the dialog's description) — the pinned header holds only icon, title and
  // close, so a long explanation never eats the space the form needs.
  description?: string;
  icon?: React.ReactNode;
  tone?: DialogTone;
  children: React.ReactNode;
  // Pinned action row. Submit buttons living here reference their form via
  // the `form` attribute (the form itself stays in the scrollable body).
  footer?: React.ReactNode;
  className?: string;
  size?: DialogSize;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();

  // onClose is often an inline arrow that changes identity every parent
  // render — keep it in a ref so the effect below runs ONLY on open/close.
  // Re-running it per keystroke would steal focus from the field being typed in.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  const stackIdRef = useRef<symbol | null>(null);
  useEffect(() => {
    if (!open) return;
    const stackId = Symbol("dialog");
    stackIdRef.current = stackId;
    openDialogStack.push(stackId);
    const prevFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Move focus into the dialog — unless an autofocused field already has it.
    if (!panelRef.current?.contains(document.activeElement)) panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      // Only the TOPMOST open dialog handles keys. For Escape that means a
      // nested create-dialog closes alone; for Tab it keeps the host's focus
      // trap from yanking focus out of the nested panel on every keypress
      // (both traps used to fight — Tab could never leave the first control).
      if (openDialogStack[openDialogStack.length - 1] !== stackId) return;
      if (e.key === "Escape") {
        // An open combobox inside the panel owns Escape: the press closes its
        // list, not the dialog. Only comboboxes -- expanded tree and section
        // toggles keep focus while open and must not swallow the key.
        if (e.target instanceof Element && e.target.closest('[role="combobox"][aria-expanded="true"]')) return;
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key === "Tab") {
        // aria-modal promises a trap: Tab cycles inside the panel instead of
        // escaping into the inert page behind the overlay.
        const panel = panelRef.current;
        if (!panel) return;
        const focusables = panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (!panel.contains(active)) {
          e.preventDefault();
          first.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        } else if (e.shiftKey && (active === first || active === panel)) {
          e.preventDefault();
          last.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey, true);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      const i = openDialogStack.indexOf(stackId);
      if (i !== -1) openDialogStack.splice(i, 1);
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      prevFocus?.focus(); // hand focus back to the control that opened us
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div aria-hidden className="absolute inset-0 bg-black/55 backdrop-blur-[3px] motion-safe:animate-[nx-fade-in_.15s_ease-out]" onMouseDown={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={cn(
          "relative flex max-h-[85vh] w-full flex-col rounded-2xl border border-line bg-surface shadow-[0_32px_90px_-28px_rgba(12,10,8,.55)] outline-none motion-safe:animate-[nx-dialog-in_.18s_ease-out]",
          DIALOG_SIZES[size],
          className,
        )}
      >
        <div className="flex flex-none items-center gap-3 px-6 pb-4 pt-5">
          {icon && <span className={cn("flex size-9 flex-none items-center justify-center rounded-xl border", DIALOG_TONES[tone])}>{icon}</span>}
          <h2 id={titleId} className="min-w-0 flex-1 truncate font-display text-[17px] font-extrabold leading-snug">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="-mr-1 flex size-7 flex-none items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink">
            <X size={16} strokeWidth={2} />
          </button>
        </div>
        <DialogBody hasFooter={!!footer}>
          {description && <p id={descId} className="mb-4 text-[13px] leading-relaxed text-ink2">{description}</p>}
          {children}
        </DialogBody>
        {footer && <div className="flex-none px-6 pb-6 pt-4">{footer}</div>}
      </div>
    </div>
  );
}

// A titled group of fields inside a dialog body. Sections are separated by a
// hairline and even vertical rhythm, so a long form reads as a few named
// steps rather than one column of inputs.
export function DialogSection({ title, hint, children, className }: {
  title: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    // No aria-label on purpose: the heading gives assistive tech the structure,
    // and a named region would answer label queries meant for the fields inside.
    <section className={cn("border-t border-line py-5 first:border-t-0 first:pt-0 last:pb-0", className)}>
      <div className="mb-3.5">
        <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
        {hint && <p className="mt-0.5 text-[12px] leading-relaxed text-ink2">{hint}</p>}
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

// One confirmation pattern for the whole app: state the action, show what it
// affects, make the destructive path visually distinct.
export function ConfirmDialog({ open, onClose, onConfirm, title, body, confirmLabel, confirmIcon, cancelLabel = "Cancel", tone = "danger", loading }: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  // Icon for the confirm button: a bin for destructive confirms, a tick for
  // neutral ones, or whatever names the action better (archive, sign out…).
  confirmIcon?: React.ReactNode;
  cancelLabel?: string;
  tone?: "danger" | "neutral";
  loading?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      icon={tone === "danger" ? <TriangleAlert size={17} strokeWidth={2} /> : <CircleAlert size={17} strokeWidth={2} />}
      tone={tone === "danger" ? "crit" : "warn"}
      footer={
        <div className="flex justify-end gap-2">
          <Button size="sm" onClick={onClose} disabled={loading}><X size={14} strokeWidth={2} /> {cancelLabel}</Button>
          <Button size="sm" variant={tone === "danger" ? "danger" : "primary"} loading={loading} onClick={onConfirm}>
            {confirmIcon ?? (tone === "danger" ? <Trash2 size={14} strokeWidth={2} /> : <Check size={14} strokeWidth={2} />)} {confirmLabel}
          </Button>
        </div>
      }
    >
      <div className="text-[13.5px] leading-relaxed text-ink2">{body}</div>
    </Dialog>
  );
}
