"use client";

import { create } from "zustand";

// Whether the app can reach anything right now. Two independent facts: the
// browser's own network (navigator.onLine, which only knows about the
// device) and the connected server (learned from calls that never arrive or
// come back from a proxy with nothing behind it). Not persisted — it is a
// live reading, and every consumer re-checks on mount.
interface ConnectivityState {
  browserOnline: boolean;
  serverDown: boolean;
  // When the server was first seen down — the banner reads it for "since".
  serverDownSince: number | null;
  setBrowserOnline: (online: boolean) => void;
  reportServerFailure: () => void;
  reportServerOk: () => void;
}

export const useConnectivity = create<ConnectivityState>()((set, get) => ({
  browserOnline: true,
  serverDown: false,
  serverDownSince: null,
  setBrowserOnline: (browserOnline) => set({ browserOnline }),
  reportServerFailure: () => {
    if (get().serverDown) return;
    set({ serverDown: true, serverDownSince: Date.now() });
  },
  reportServerOk: () => {
    if (!get().serverDown) return;
    set({ serverDown: false, serverDownSince: null });
  },
}));

// The statuses a proxy answers with when nothing is behind it (nginx up,
// nucleus down) — as good as unreachable from the user's point of view.
export const GATEWAY_STATUSES = new Set([502, 503, 504]);
