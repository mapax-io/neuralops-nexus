import type { ServerConnection } from "@/stores/connection.store";

export interface ServerConfig {
  server_url?: string;
  server_version?: string | null;
  nucleus_version?: string | null;
  nexus_ai_version?: string | null;
  nexus_transport_version?: string | null;
}

// Public, unauthenticated — used for the per-card version preview before connect.
export async function fetchServerConfig(url: string): Promise<ServerConfig | null> {
  try {
    const res = await fetch(`${url}/api/v1/auth/config/`);
    if (!res.ok) return null;
    return (await res.json()) as ServerConfig;
  } catch {
    return null;
  }
}

interface VerifyResponse {
  ok: boolean;
  user_id?: string;
  email?: string;
  is_new_user?: boolean; // the server just created this member on this connect
  company_exists?: boolean;
  is_owner?: boolean;
  role?: string | null;
  company_name?: string | null;
  server_version?: string | null;
  nucleus_version?: string | null;
  nexus_ai_version?: string | null;
  nexus_transport_version?: string | null;
}

export type ConnectOutcome =
  | { kind: "ok"; connection: ServerConnection; isNewUser: boolean }
  | { kind: "not-member" }
  | { kind: "not-set-up" }
  | { kind: "unreachable" }
  | { kind: "error"; status: number; message: string };

// The real "connect" call. Side effects on the server: creates the local user
// record and auto-accepts any pending invitation for this email.
export async function connectToServer(url: string, token: string): Promise<ConnectOutcome> {
  let res: Response;
  try {
    res = await fetch(`${url}/api/v1/auth/verify/`, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    return { kind: "unreachable" };
  }
  if (res.status === 403) return { kind: "not-member" };
  if (!res.ok) return { kind: "error", status: res.status, message: `Server returned ${res.status}.` };
  let data: VerifyResponse;
  try {
    data = (await res.json()) as VerifyResponse;
  } catch {
    // A 200 with a non-JSON body (nginx default page, captive portal, wrong
    // reverse proxy) must not escape the ConnectOutcome contract.
    return { kind: "error", status: res.status, message: "That address answered, but not like a NeuralOps server — check the URL." };
  }
  if (data.company_exists === false) return { kind: "not-set-up" };
  return {
    kind: "ok",
    isNewUser: Boolean(data.is_new_user),
    connection: {
      serverUrl: url,
      nucleusUserId: data.user_id,
      role: data.role ?? null,
      isOwner: Boolean(data.is_owner),
      companyName: data.company_name ?? null,
      serverVersion: data.server_version ?? null,
      moduleVersions: {
        nucleus: data.nucleus_version ?? undefined,
        nexusAi: data.nexus_ai_version ?? undefined,
        transport: data.nexus_transport_version ?? undefined,
      },
    },
  };
}
