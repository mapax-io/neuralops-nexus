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

export async function resetPassword(email: string): Promise<void> {
  const { error } = await getSupabase().auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/reset-password`,
  });
  if (error) throw new Error(error.message);
}

export async function updatePassword(newPassword: string): Promise<void> {
  const { error } = await getSupabase().auth.updateUser({ password: newPassword });
  if (error) throw new Error(error.message);
}

export async function getCurrentSession() {
  const { data } = await getSupabase().auth.getSession();
  return data.session;
}

export interface VerifyResult {
  ok: boolean;
  status: number;
  // populated when ok === true
  userId?: string;
  role?: string;
  companyName?: string;
  isOwner?: boolean;
}

/** Verify the Supabase JWT against a Django NeuralOps server. */
export async function verifyServerAccess(
  serverUrl: string,
  token: string,
): Promise<VerifyResult> {
  try {
    const res = await fetch(`${serverUrl}/api/v1/auth/verify/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      return {
        ok: true,
        status: res.status,
        userId: data.user_id,
        role: data.role ?? null,
        companyName: data.company_name ?? null,
        isOwner: data.is_owner ?? false,
      };
    }
    return { ok: false, status: res.status };
  } catch {
    return { ok: false, status: 0 };
  }
}
