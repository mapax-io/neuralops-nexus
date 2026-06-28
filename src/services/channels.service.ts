import { apiJson } from "./api.client";
import type { Channel } from "@/types";

export async function listChannels(projectId: string): Promise<Channel[]> {
  return apiJson<Channel[]>(`/api/v1/projects/${projectId}/channels/`);
}

export async function createChannel(
  projectId: string,
  input: Partial<Channel>,
): Promise<Channel> {
  return apiJson<Channel>(`/api/v1/projects/${projectId}/channels/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
