import { create } from "zustand";

export interface UIState {
  activeTopicId: string | null;
  sidebarCollapsed: boolean;
  setActiveTopicId: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeTopicId: null,
  sidebarCollapsed: false,
  setActiveTopicId: (activeTopicId) => set({ activeTopicId }),
  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
}));
