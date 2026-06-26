const BASE_URL = import.meta.env.VITE_API_URL;

export interface InitResponse {
  status: "authenticated" | "unauthenticated";
  email?: string;
  user_id?: string;
  session_expires_at?: string;
  login_url?: string;
}

export interface StatusResponse {
  status: "pending" | "active" | "session_expired";
  email?: string;
  user_id?: string;
  session_expires_at?: string;
}

export async function getAuthInit(): Promise<InitResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/init/`);
  if (!res.ok) throw new Error("Failed to reach backend");
  return res.json();
}

export async function getAuthStatus(): Promise<StatusResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/status/`);
  if (!res.ok) throw new Error("Failed to reach backend");
  return res.json();
}
