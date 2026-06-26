import { create } from "zustand";

interface UiState {
  activeTopicId: string | null;
  sidebarOpen: boolean;
  setActiveTopicId: (id: string | null) => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeTopicId: null,
  sidebarOpen: true,
  setActiveTopicId: (activeTopicId) => set({ activeTopicId }),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
