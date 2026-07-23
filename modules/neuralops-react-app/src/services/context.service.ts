import { useAuthStore } from "@/store/auth.store";
import { ApiError } from "./api-client";

export interface ContextSource {
  id: string;
  topic_id: string;
  type: string;
  name: string;
  url?: string | null;
  collection_id: string;
  status: string;
  error?: string | null;
  created_at: string;
}

export interface ContextDirective {
  directive: string;
  help: string;
}

function getBaseHeaders(): Record<string, string> {
  const { supabaseToken } = useAuthStore.getState();
  return supabaseToken ? { Authorization: `Bearer ${supabaseToken}` } : {};
}

function getServerUrl(): string {
  const { serverUrl } = useAuthStore.getState();
  if (!serverUrl) throw new ApiError(0, "No server selected");
  return serverUrl;
}

export async function listContextSources(
  projectId: string,
  topicId: string,
): Promise<ContextSource[]> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-sources/`,
    { headers: getBaseHeaders() },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function attachFileContext(
  projectId: string,
  topicId: string,
  file: File,
): Promise<ContextSource> {
  const { supabaseToken } = useAuthStore.getState();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-sources/file/`,
    {
      method: "POST",
      headers: supabaseToken ? { Authorization: `Bearer ${supabaseToken}` } : {},
      body: formData,
    },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function attachUrlContext(
  projectId: string,
  topicId: string,
  url: string,
  name?: string,
): Promise<ContextSource> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-sources/web/`,
    {
      method: "POST",
      headers: { ...getBaseHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ url, name }),
    },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function detachContextSource(
  projectId: string,
  topicId: string,
  sourceId: string,
): Promise<void> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-sources/${sourceId}/`,
    { method: "DELETE", headers: getBaseHeaders() },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
}

// ── Context Panel (M6) ──────────────────────────────────────────────────────

export interface ContextPanelItem {
  id: string;
  label: string;
  deletable: boolean;
  metadata: Record<string, unknown>;
}

export interface ContextPanelGroup {
  directive: string;
  label: string;
  icon: string;
  can_delete_source: boolean;
  can_delete_items: boolean;
  items: ContextPanelItem[];
}

export interface PanelDeleteRequest {
  items: { directive: string; id: string }[];
}

export async function getContextPanel(
  projectId: string,
  topicId: string,
): Promise<ContextPanelGroup[]> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-panel/`,
    { headers: getBaseHeaders() },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function deleteContextPanelItems(
  projectId: string,
  topicId: string,
  items: { directive: string; id: string }[],
): Promise<{ ok: boolean; deleted: string[] }> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/${projectId}/topics/${topicId}/context-panel/items/`,
    {
      method: "DELETE",
      headers: { ...getBaseHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export async function listDirectives(): Promise<ContextDirective[]> {
  const res = await fetch(
    `${getServerUrl()}/api/v1/projects/context-sources/directives/`,
    { headers: getBaseHeaders() },
  );
  if (!res.ok) return [];
  return res.json();
}
