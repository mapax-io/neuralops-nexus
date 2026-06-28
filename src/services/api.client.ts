import { useAuthStore } from "@/store/auth.store";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function apiRequest(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { serverUrl, supabaseToken } = useAuthStore.getState();
  if (!serverUrl) throw new ApiError(0, "No server selected");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (supabaseToken) headers.Authorization = `Bearer ${supabaseToken}`;

  return fetch(`${serverUrl}${path}`, { ...options, headers });
}

export async function apiJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await apiRequest(path, options);
  if (!res.ok) {
    throw new ApiError(res.status, await res.text().catch(() => res.statusText));
  }
  return res.json() as Promise<T>;
}
