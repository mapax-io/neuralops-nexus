import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthState {
  userId: string | null;
  email: string | null;
  sessionExpiresAt: string | null;
  setIdentity: (userId: string, email: string, sessionExpiresAt: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      userId: null,
      email: null,
      sessionExpiresAt: null,
      setIdentity: (userId, email, sessionExpiresAt) =>
        set({ userId, email, sessionExpiresAt }),
      clearAuth: () =>
        set({ userId: null, email: null, sessionExpiresAt: null }),
    }),
    {
      name: "neuralops-auth",
      partialize: (s) => ({
        userId: s.userId,
        email: s.email,
        sessionExpiresAt: s.sessionExpiresAt,
      }),
    },
  ),
);
