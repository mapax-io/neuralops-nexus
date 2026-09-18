"use client";

import { useEffect } from "react";
import { clearAccountScopedState } from "@/lib/auth/session-cleanup";
import { supabase } from "@/lib/supabase";
import { useConnectionStore } from "@/stores/connection.store";

// How long the first session read may take before the app stops waiting on
// it. supabase-js guards the stored session with navigator.locks; a lock left
// held by another tab (one killed mid-refresh, an old build across a deploy)
// makes getSession() wait forever, and every page holds its loader on
// `hydrated`. A late answer still lands through the auth listener.
const HYDRATION_WATCHDOG_MS = 8_000;

// Keeps the connection store's identity in sync with the Supabase session:
// hydrates on load, follows sign-in/out and token refreshes.
export function SupabaseSessionSync() {
  useEffect(() => {
    // Design fixtures under /dev/* drive the stores themselves (dev builds only).
    if (process.env.NODE_ENV !== "production" && window.location.pathname.startsWith("/dev/")) return;
    const sb = supabase();
    const settle = () => {
      if (!useConnectionStore.getState().hydrated) useConnectionStore.setState({ hydrated: true });
    };
    const watchdog = window.setTimeout(settle, HYDRATION_WATCHDOG_MS);
    sb.auth
      .getSession()
      .then(({ data }) => {
        const s = data.session;
        if (s?.user) useConnectionStore.getState().setIdentity(s.access_token, s.user.id, s.user.email ?? "");
      })
      .catch(() => undefined) // a failed read is "no session", not a frozen app
      .finally(() => {
        window.clearTimeout(watchdog);
        settle();
      });
    const { data: sub } = sb.auth.onAuthStateChange((event, s) => {
      // A session can end WITHOUT a sign-out button: expiry, revocation, or
      // sign-out in another tab all land here — and must clear exactly what
      // the buttons clear, or the next account inherits this one's state.
      if (event === "SIGNED_OUT" || !s?.user) clearAccountScopedState();
      else useConnectionStore.getState().setIdentity(s.access_token, s.user.id, s.user.email ?? "");
      settle();
    });
    return () => {
      window.clearTimeout(watchdog);
      sub.subscription.unsubscribe();
    };
  }, []);
  return null;
}
