"use client";

import { useEffect, useId, useRef, useState } from "react";
import { TriangleAlert, X } from "lucide-react";
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

const DIALOG_SIZES = {
  sm: "max-w-md",   // confirmations
  md: "max-w-xl",   // simple one-or-two-field forms (default)
  lg: "max-w-3xl",  // multi-field forms
  xl: "max-w-3xl",  // dense forms / lists
  "2xl": "max-w-4xl", // wide forms (MCP + OAuth setup)
} as const;

export type DialogSize = keyof typeof DIALOG_SIZES;

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

export function Dialog({ open, onClose, title, description, icon, children, footer, className, size = "md" }: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  // Pinned action row. Submit buttons living here reference their form via
  // the `form` attribute (the form itself stays in the scrollable body).
  footer?: React.ReactNode;
  className?: string;
  size?: DialogSize;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

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
        tabIndex={-1}
        className={cn(
          "relative flex max-h-[85vh] w-full flex-col rounded-2xl border border-line bg-surface shadow-[0_32px_90px_-28px_rgba(12,10,8,.55)] outline-none motion-safe:animate-[nx-dialog-in_.18s_ease-out]",
          DIALOG_SIZES[size],
          className,
        )}
      >
        <div className="flex flex-none items-start gap-3 px-6 pb-4 pt-6">
          {icon && <span className="mt-0.5 flex size-9 flex-none items-center justify-center rounded-xl border border-line bg-surface2">{icon}</span>}
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="font-display text-[17px] font-extrabold leading-snug">{title}</h2>
            {description && <p className="mt-1 text-[13px] leading-relaxed text-ink2">{description}</p>}
          </div>
          <button aria-label="Close" onClick={onClose} className="-mr-1 -mt-1 flex size-7 flex-none items-center justify-center rounded-md text-ink2 hover:bg-surface2 hover:text-ink">
            <X size={16} strokeWidth={2} />
          </button>
        </div>
        <DialogBody hasFooter={!!footer}>{children}</DialogBody>
        {footer && <div className="flex-none px-6 pb-6 pt-4">{footer}</div>}
      </div>
    </div>
  );
}

// One confirmation pattern for the whole app: state the action, show what it
// affects, make the destructive path visually distinct.
export function ConfirmDialog({ open, onClose, onConfirm, title, body, confirmLabel, cancelLabel = "Cancel", tone = "danger", loading }: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
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
      icon={tone === "danger" ? <TriangleAlert size={17} strokeWidth={2} className="text-crit" /> : undefined}
      footer={
        <div className="flex justify-end gap-2">
          <Button size="sm" onClick={onClose} disabled={loading}>{cancelLabel}</Button>
          <Button size="sm" variant={tone === "danger" ? "danger" : "primary"} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      }
    >
      <div className="text-[13.5px] leading-relaxed text-ink2">{body}</div>
    </Dialog>
  );
}
