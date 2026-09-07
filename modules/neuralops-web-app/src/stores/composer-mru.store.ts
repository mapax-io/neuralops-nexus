"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

// Composer "recently used" for the @ (personas) and / (commands) popovers, so
// the things you reach for most float to the top for quicker selection.
//
// State class (account- vs device-scoped): DEVICE-SCOPED, but
// CLEARED ON SIGN-OUT for privacy — exactly like `nx-selection` (workspace
// selection). It is genuinely about this device (a convenience ordering, not
// account data the user expects to follow them across browsers), yet leaving a
// previous user's recent persona names in the popover for the next account on
// the same browser would leak who they were talking to. So: not synced, and
// wiped by clearAccountScopedState() in lib/auth/session-cleanup.ts.

export const MRU_CAP = 8; // short enough that the list still means "recent"

/** Put `name` at the front, deduped case-insensitively, capped to `cap`. Pure. */
export function bumpRecent(list: string[], name: string, cap = MRU_CAP): string[] {
  const lower = name.toLowerCase();
  return [name, ...list.filter((n) => n.toLowerCase() !== lower)].slice(0, cap);
}

/**
 * Return a copy of `items` with the ones whose `key` is in `recents` floated to
 * the front in recents-order; everything else keeps its original order (sort is
 * stable). Recents not present in `items` are ignored. Pure — never mutates.
 */
export function orderByRecency<T>(items: T[], key: (t: T) => string, recents: string[]): T[] {
  if (recents.length === 0) return items;
  const rank = new Map(recents.map((r, i) => [r.toLowerCase(), i]));
  return [...items].sort(
    (a, b) => (rank.get(key(a).toLowerCase()) ?? Infinity) - (rank.get(key(b).toLowerCase()) ?? Infinity),
  );
}

interface ComposerMruState {
  personas: string[]; // recent persona names, most-recent-first
  commands: string[]; // recent slash command names, most-recent-first
  recordPersona: (name: string) => void;
  recordCommand: (name: string) => void;
  clear: () => void;
}

export const useComposerMruStore = create<ComposerMruState>()(
  persist(
    (set) => ({
      personas: [],
      commands: [],
      recordPersona: (name) => set((s) => ({ personas: bumpRecent(s.personas, name) })),
      recordCommand: (name) => set((s) => ({ commands: bumpRecent(s.commands, name) })),
      clear: () => set({ personas: [], commands: [] }),
    }),
    { name: "nx-composer-mru" },
  ),
);
