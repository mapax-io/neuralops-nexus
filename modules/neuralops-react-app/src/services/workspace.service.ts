import { apiRequest } from "./api-client";

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
