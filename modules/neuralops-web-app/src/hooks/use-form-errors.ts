"use client";

import { useEffect, useRef, useState } from "react";

// Is a pointer button held down right now? Blur fires on pointerdown, so a
// message revealed by it would move the content — and the button being
// pressed — before pointerup, and the click would miss. Reveals wait for the
// press to end (and one tick more, so the click has been dispatched).
let pressed = false;
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", () => { pressed = true; }, true);
  document.addEventListener("pointerup", () => { pressed = false; }, true);
  document.addEventListener("pointercancel", () => { pressed = false; }, true);
}
export function afterPress(fn: () => void) {
  if (!pressed) return fn();
  const done = () => {
    document.removeEventListener("pointerup", done, true);
    document.removeEventListener("pointercancel", done, true);
    setTimeout(fn, 0);
  };
  document.addEventListener("pointerup", done, true);
  document.addEventListener("pointercancel", done, true);
}

export const isBlank = (v: unknown) =>
  v == null || v === false || (typeof v === "string" && v.trim() === "") || (Array.isArray(v) && v.length === 0);

// A rule is the field's message (or null), optionally paired with the value
// it judges: `[value, message]`. With the value known, a pristine empty field
// stays quiet when left — the asterisk and the disabled button carry it —
// while a field that has held a value (typed, or pre-filled from the record
// being edited) and is then emptied does speak up.
type Rule = string | null | undefined | readonly [value: unknown, problem: string | null | undefined];
const problemOf = (r: Rule) => (Array.isArray(r) ? (r[1] as string | null | undefined) : (r as string | null | undefined));

// Field-level validation for a form whose rules are plain functions. The
// caller recomputes `rules` every render, so the submit button derives from
// every rule at once while a field's message shows only after touch(k) — the
// blur that judges it; from then on the message follows the value live.
// touchAll() is for a submit that got through anyway (Enter, a stale list,
// tests): it reveals everything at once.
export function useFormErrors<K extends string>(rules: Record<K, Rule>) {
  const [touched, setTouched] = useState<{ all: boolean; keys: Partial<Record<K, true>> }>({ all: false, keys: {} });
  const seen = useRef(new Set<K>());
  const keys = Object.keys(rules) as K[];
  useEffect(() => {
    for (const k of keys) {
      const r = rules[k];
      if (Array.isArray(r) && !isBlank(r[0])) seen.current.add(k);
    }
  });
  const invalid = keys.some((k) => !!problemOf(rules[k]));
  return {
    invalid,
    error: (k: K): string | null => (touched.all || touched.keys[k] ? problemOf(rules[k]) ?? null : null),
    touch: (k: K) => {
      const r = rules[k];
      if (Array.isArray(r) && isBlank(r[0]) && !seen.current.has(k)) return;
      afterPress(() => setTouched((t) => (t.keys[k] ? t : { ...t, keys: { ...t.keys, [k]: true } })));
    },
    touchAll: () => setTouched((t) => (t.all ? t : { ...t, all: true })),
    reset: () => {
      seen.current.clear();
      setTouched({ all: false, keys: {} });
    },
  };
}
