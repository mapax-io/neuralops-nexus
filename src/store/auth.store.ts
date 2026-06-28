import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthState {
  supabaseToken: string | null;
  userId: string | null;
  email: string | null;
  serverUrl: string | null;

  setIdentity: (token: string, userId: string, email: string) => void;
  setServerUrl: (url: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      supabaseToken: null,
      userId: null,
      email: null,
      serverUrl: null,
      setIdentity: (supabaseToken, userId, email) =>
        set({ supabaseToken, userId, email }),
      setServerUrl: (serverUrl) => set({ serverUrl }),
      clearAuth: () =>
        set({ supabaseToken: null, userId: null, email: null, serverUrl: null }),
    }),
    {
      name: "neuralops-auth",
      partialize: (s) => ({
        supabaseToken: s.supabaseToken,
        userId: s.userId,
        email: s.email,
        serverUrl: s.serverUrl,
      }),
    },
  ),
);
