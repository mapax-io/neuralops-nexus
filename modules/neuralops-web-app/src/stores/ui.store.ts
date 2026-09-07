"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

// DEVICE-SCOPED (like nx-theme): pure layout preference, no personal data —
// deliberately NOT cleared on sign-out.
interface UiState {
  chatsPanelCollapsed: boolean;
  toggleChatsPanel: () => void;
  // The Intelligence section currently in view — the single source of truth
  // shared by the /intelligence page and the top bar's active states.
  intelSection: string;
  setIntelSection: (s: string) => void;
  // One-shot intent from slash commands (/add-model etc.): the matching
  // intelligence tab opens its create dialog once, then clears this.
  intelCreate: boolean;
  setIntelCreate: (v: boolean) => void;
  // The project the Intelligence area is looking at (personas are per project)
  // — shared so the nav's setup guide and the personas tab agree. Not
  // persisted: it is a view choice, not a preference.
  intelProject?: string;
  setIntelProject: (id: string | undefined) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      chatsPanelCollapsed: false,
      toggleChatsPanel: () => set({ chatsPanelCollapsed: !get().chatsPanelCollapsed }),
      intelSection: "personas",
      setIntelSection: (s) => set({ intelSection: s }),
      intelCreate: false,
      setIntelCreate: (v) => set({ intelCreate: v }),
      intelProject: undefined,
      setIntelProject: (id) => set({ intelProject: id }),
    }),
    { name: "nx-ui", partialize: (s) => ({ chatsPanelCollapsed: s.chatsPanelCollapsed }) },
  ),
);
