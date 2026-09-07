import { useConnectionStore } from "@/stores/connection.store";
import { GATEWAY_STATUSES, useConnectivity } from "@/lib/connectivity";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function extractMessage(status: number, body: string): string {
  try {
    const data = JSON.parse(body) as { detail?: unknown; message?: unknown };
    if (typeof data.detail === "string") return data.detail;
    // Django Ninja validation errors: detail is an array of {loc, msg, type}.
    // Users must never see the raw JSON blob in a toast.
    if (Array.isArray(data.detail)) {
      const first = data.detail[0] as { msg?: unknown; loc?: unknown[] } | undefined;
      const field = Array.isArray(first?.loc) ? String(first.loc.at(-1)) : null;
      const msg = typeof first?.msg === "string" ? first.msg : "a value was rejected";
      return field ? `The server rejected "${field}": ${msg}.` : `The server rejected the request: ${msg}.`;
    }
    if (typeof data.message === "string") return data.message;
  } catch {
    /* not JSON */
  }
  // Proxy/HTML error pages (nginx 502…) are not user-facing copy.
  if (body.trimStart().startsWith("<")) return `The server had a problem (HTTP ${status}) — try again in a moment.`;
  return body.slice(0, 200) || `Server returned ${status}.`;
}

// One client for every nucleus call: active-server base URL, bearer auth,
// 204 → undefined, error envelope normalization, status 0 on network failure.
export async function apiJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { serverUrl, token } = useConnectionStore.getState();
  if (!serverUrl) throw new ApiError(0, "No server connected.");
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${serverUrl}${path}`, { ...options, headers });
  } catch {
    // Every call reports here so the connectivity banner learns about a
    // server that went away without any screen having to watch for it.
    useConnectivity.getState().reportServerFailure();
    throw new ApiError(0, "Could not reach the server.");
  }
  if (GATEWAY_STATUSES.has(res.status)) {
    useConnectivity.getState().reportServerFailure();
    throw new ApiError(res.status, extractMessage(res.status, await res.text()));
  }
  useConnectivity.getState().reportServerOk();
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw new ApiError(res.status, extractMessage(res.status, await res.text()));
  return (await res.json()) as T;
}

// Avatar/media paths from the API are server-relative; render them against
// the active server (a missing prefix silently breaks avatars).
export function absolutizeMedia<T extends string | null | undefined>(path: T): T | string {
  // Absolute, protocol-relative, and data: URLs pass through untouched —
  // prefixing them would produce "http://server//cdn…" garbage.
  if (!path || /^(https?:)?\/\//.test(path) || path.startsWith("data:")) return path;
  const { serverUrl } = useConnectionStore.getState();
  return serverUrl ? `${serverUrl}${path.startsWith("/") ? "" : "/"}${path}` : path;
}
