import { apiJson } from "./api.client";
import type { Topic } from "@/types";

export async function listTopics(channelId: string): Promise<Topic[]> {
  return apiJson<Topic[]>(`/api/v1/channels/${channelId}/topics/`);
}

export async function createTopic(
  channelId: string,
  input: Partial<Topic>,
): Promise<Topic> {
  return apiJson<Topic>(`/api/v1/channels/${channelId}/topics/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
