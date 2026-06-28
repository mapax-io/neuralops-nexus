import { getSupabase } from "@/lib/supabase";

export async function signInWithEmail(email: string, password: string) {
  const { data, error } = await getSupabase().auth.signInWithPassword({
    email,
    password,
  });
  if (error) throw error;
  return data;
}

export async function signUpWithEmail(email: string, password: string) {
  const { data, error } = await getSupabase().auth.signUp({
    email,
    password,
    options: { emailRedirectTo: window.location.origin },
  });
  if (error) throw error;
  return data;
}

export async function signInWithGitHub() {
  const { data, error } = await getSupabase().auth.signInWithOAuth({
    provider: "github",
    options: { redirectTo: window.location.origin },
  });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const { error } = await getSupabase().auth.signOut();
  if (error) throw error;
}

export async function getCurrentSession() {
  const { data } = await getSupabase().auth.getSession();
  return data.session;
}

/** Verify the Supabase JWT against a Django NeuralOps server. */
export async function verifyServerAccess(
  serverUrl: string,
  token: string,
): Promise<{ ok: boolean; status: number }> {
  try {
    const res = await fetch(`${serverUrl}/api/v1/auth/verify/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return { ok: res.ok, status: res.status };
  } catch {
    return { ok: false, status: 0 };
  }
}
