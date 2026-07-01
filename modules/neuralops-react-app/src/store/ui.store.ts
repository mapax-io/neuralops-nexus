import { create } from "zustand";

export interface UIState {
  activeProjectId: string | null;
  activeChannelId: string | null;
  activeTopicId: string | null;
  sidebarCollapsed: boolean;
  setActiveTopic: (
    projectId: string,
    channelId: string,
    topicId: string,
  ) => void;
  clearActiveTopic: () => void;
  setActiveTopicId: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeProjectId: null,
  activeChannelId: null,
  activeTopicId: null,
  sidebarCollapsed: false,
  setActiveTopic: (activeProjectId, activeChannelId, activeTopicId) =>
    set({ activeProjectId, activeChannelId, activeTopicId }),
  clearActiveTopic: () =>
    set({
      activeProjectId: null,
      activeChannelId: null,
      activeTopicId: null,
    }),
  setActiveTopicId: (activeTopicId) => set({ activeTopicId }),
  toggleSidebar: () =>
    set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
}));
