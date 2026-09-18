"use client";

import { clearAccountScopedState } from "@/lib/auth/session-cleanup";
import { supabase } from "@/lib/supabase";

// Ends the session on this device: one shared cleanup (stores, drafts, query
// cache, realtime), then the provider. Local state is cleared regardless of
// the provider call -- the session dies here either way. Callers decide where
// to go next.
export async function signOutOnThisDevice(): Promise<void> {
  clearAccountScopedState();
  try {
    await supabase().auth.signOut();
  } catch {
    /* the provider may be unreachable; the device is signed out all the same */
  }
}
