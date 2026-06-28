import { useEffect } from "react";
import { getSupabase } from "@/lib/supabase";
import { useAuthStore } from "@/store/auth.store";

/**
 * Keeps the Zustand auth store in sync with Supabase's session.
 * Mount once at the app root.
 */
export function useSupabaseSessionSync() {
  const setIdentity = useAuthStore((s) => s.setIdentity);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  useEffect(() => {
    let mounted = true;

    // Hydrate from any existing session.
    getSupabase()
      .auth.getSession()
      .then(({ data }) => {
        if (!mounted) return;
        const s = data.session;
        if (s?.access_token && s.user) {
          setIdentity(s.access_token, s.user.id, s.user.email ?? "");
        }
      })
      .catch(() => {
        /* env not set — login page will surface it */
      });

    let unsub: (() => void) | undefined;
    try {
      const { data } = getSupabase().auth.onAuthStateChange((event, session) => {
        if (event === "SIGNED_OUT") {
          clearAuth();
          return;
        }
        if (session?.access_token && session.user) {
          setIdentity(
            session.access_token,
            session.user.id,
            session.user.email ?? "",
          );
        }
      });
      unsub = () => data.subscription.unsubscribe();
    } catch {
      /* ignore */
    }

    return () => {
      mounted = false;
      unsub?.();
    };
  }, [setIdentity, clearAuth]);
}
