import { apiRequest } from "./api-client";

// ── Team types ────────────────────────────────────────────────────────────────

export interface TeamMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  member_type: "human" | "persona";
  avatar: string | null;
}

export interface AvailableUser {
  user_id: string;
  name: string;
  email: string;
  avatar: string | null;
}

export interface AvailablePersona {
  persona_id: string;
  user_id: string;
  name: string;
  source_type: "model" | "agent";
  avatar: string | null;
}

export interface Channel {
  id: string;
  name: string;
  slug: string;
  description: string | null;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  channels: Channel[];
}

export interface Topic {
  id: string;
  title: string;
  slug: string;
  channel_id: string;
  project_id: string;
}

export async function getProjects(): Promise<Project[]> {
  const res = await apiRequest("/api/v1/projects/");
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function createProject(payload: {
  name: string;
  description?: string;
}): Promise<Project> {
  const res = await apiRequest("/api/v1/projects/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? "Failed to create project");
  return data;
}

export async function getTopics(
  projectId: string,
  channelId: string,
): Promise<Topic[]> {
  const res = await apiRequest(
    `/api/v1/projects/${projectId}/channels/${channelId}/topics/`,
  );
  if (!res.ok) throw new Error("Failed to fetch topics");
  return res.json();
}

export async function createChannel(
  projectId: string,
  payload: { name: string; description?: string },
): Promise<Channel> {
  const res = await apiRequest(`/api/v1/projects/${projectId}/channels/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? "Failed to create channel");
  return data;
}

export async function createTopic(
  projectId: string,
  channelId: string,
  payload: { title: string },
): Promise<Topic> {
  const res = await apiRequest(
    `/api/v1/projects/${projectId}/channels/${channelId}/topics/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? "Failed to create topic");
  return data;
}

// ── Team API ───────────────────────────────────────────────────────────────────

export async function getTeam(projectId: string): Promise<TeamMember[]> {
  const res = await apiRequest(`/api/v1/projects/${projectId}/team/`);
  if (!res.ok) throw new Error("Failed to fetch team");
  return res.json();
}

export async function addTeamMember(
  projectId: string,
  payload: { user_id: string; role?: string },
): Promise<TeamMember> {
  const res = await apiRequest(`/api/v1/projects/${projectId}/team/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? "Failed to add member");
  return data;
}

export async function removeTeamMember(
  projectId: string,
  userId: string,
): Promise<void> {
  const res = await apiRequest(`/api/v1/projects/${projectId}/team/${userId}/`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to remove member");
}

export async function inviteToProject(
  projectId: string,
  payload: { email: string; scope?: string; topic_id?: string; role?: string },
): Promise<{ ok: boolean; message: string; is_new_user: boolean; server_url?: string }> {
  const res = await apiRequest(`/api/v1/projects/${projectId}/team/invite/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    // Try JSON first (Ninja error), fall back to raw text (Django 500 HTML)
    const raw = await res.text().catch(() => `HTTP ${res.status}`);
    let detail: string;
    try {
      const parsed = JSON.parse(raw);
      detail = parsed.detail ?? parsed.message ?? raw;
    } catch {
      // Strip HTML tags to get a readable string from Django debug pages
      detail = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 200);
    }
    throw new Error(detail);
  }
  const data = await res.json();
  return data;
}

export async function getAvailableUsers(
  projectId: string,
  search = "",
): Promise<AvailableUser[]> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : "";
  const res = await apiRequest(
    `/api/v1/projects/${projectId}/team/available-users/${qs}`,
  );
  if (!res.ok) throw new Error("Failed to fetch available users");
  return res.json();
}

export async function getAvailablePersonas(
  projectId: string,
): Promise<AvailablePersona[]> {
  const res = await apiRequest(
    `/api/v1/projects/${projectId}/team/available-personas/`,
  );
  if (!res.ok) throw new Error("Failed to fetch available personas");
  return res.json();
}
