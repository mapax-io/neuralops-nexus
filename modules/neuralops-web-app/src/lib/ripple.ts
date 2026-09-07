// Press feedback, delegated: what counts as clickable, and the ripple's
// geometry. Pure so the rules are testable without a DOM event in flight.

// Must match the nx-ripple animation length in globals.css.
export const RIPPLE_MS = 600;
// A touch that starts on a control is as likely a scroll as a tap — wait this
// long, and let a move past the threshold cancel it (Material does the same).
export const TOUCH_ARM_MS = 80;
export const TOUCH_CANCEL_PX = 6;
// Checkboxes and radios are too small to clip a ripple to; they get a round
// halo this many times their size instead.
export const HALO_SCALE = 2.4;

export const RIPPLE_TARGETS = [
  "button",
  "a[href]",
  "summary",
  '[role="button"]',
  '[role="menuitem"]',
  '[role="menuitemradio"]',
  '[role="menuitemcheckbox"]',
  '[role="tab"]',
  '[role="option"]',
  '[role="switch"]',
  '[role="treeitem"]',
  '[role="link"]',
  'input[type="checkbox"]',
  'input[type="radio"]',
  'input[type="button"]',
  'input[type="submit"]',
  'input[type="reset"]',
  "[data-ripple]",
].join(", ");

// Typing surfaces and explicit opt-outs win over any interactive ancestor —
// a click that places the caret is not a press.
const RIPPLE_STOPS = [
  'input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="reset"])',
  "textarea",
  "select",
  '[contenteditable]:not([contenteditable="false"])',
  ".ProseMirror",
  '[data-ripple="off"]',
].join(", ");

export interface FindOptions {
  // Inline text links (display: inline) read wrong with a rect ripple; the
  // caller supplies the computed-style check so this stays DOM-free.
  isInline?: (el: Element) => boolean;
}

export function findRippleTarget(start: Element | null, opts: FindOptions = {}): Element | null {
  if (!start) return null;
  if (start.closest(RIPPLE_STOPS)) return null;
  const el = start.closest(RIPPLE_TARGETS);
  if (!el) return null;
  if (el.matches(":disabled") || el.getAttribute("aria-disabled") === "true") return null;
  if (el.tagName === "A" && opts.isInline?.(el)) return null;
  return el;
}

export function isHaloTarget(el: Element): boolean {
  if (el instanceof HTMLInputElement) return el.type === "checkbox" || el.type === "radio";
  return el.getAttribute("role") === "switch";
}

export interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface RippleGeometry {
  // The clip box, in viewport coordinates.
  left: number;
  top: number;
  width: number;
  height: number;
  // The ripple's origin inside the clip box, and its final diameter.
  x: number;
  y: number;
  diameter: number;
  halo: boolean;
}

// The circle grows until it covers the farthest corner of the clip box, so a
// press anywhere ends with the whole control washed once.
export function rippleGeometry(rect: RectLike, point: { x: number; y: number } | null, halo: boolean): RippleGeometry {
  if (halo) {
    const size = Math.max(rect.width, rect.height) * HALO_SCALE;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    return { left: cx - size / 2, top: cy - size / 2, width: size, height: size, x: size / 2, y: size / 2, diameter: size, halo: true };
  }
  const x = point ? point.x - rect.left : rect.width / 2;
  const y = point ? point.y - rect.top : rect.height / 2;
  const radius = Math.max(
    Math.hypot(x, y),
    Math.hypot(rect.width - x, y),
    Math.hypot(x, rect.height - y),
    Math.hypot(rect.width - x, rect.height - y),
  );
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height, x, y, diameter: radius * 2, halo: false };
}
