import { apiJson, apiRequest } from "./api.client";
import type { Message } from "@/types";
import { useAuthStore } from "@/store/auth.store";

export async function listMessages(topicId: string): Promise<Message[]> {
  return apiJson<Message[]>(`/api/v1/topics/${topicId}/messages/`);
}

export async function sendMessage(
  topicId: string,
  input: Partial<Message>,
): Promise<Message> {
  return apiJson<Message>(`/api/v1/topics/${topicId}/messages/`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Open an SSE stream for messages on a topic. */
export function streamMessages(topicId: string): EventSource {
  const { serverUrl, supabaseToken } = useAuthStore.getState();
  const url = new URL(`${serverUrl}/api/v1/topics/${topicId}/stream/`);
  if (supabaseToken) url.searchParams.set("token", supabaseToken);
  return new EventSource(url.toString());
}

export { apiRequest };
