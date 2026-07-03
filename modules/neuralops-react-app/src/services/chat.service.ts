import { apiRequest } from "./api-client";

export interface SendMessagePayload {
  content: string;
  type?: "text";
  topic_id?: string;
  channel_id: string;
  project_id: string;
}

export interface SendMessageResponse {
  topic_id: string;
  message_id: string;
}

export async function sendMessage(
  payload: SendMessagePayload,
): Promise<SendMessageResponse> {
  const res = await apiRequest("/api/v1/chat/messages/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? "Failed to send message");
  return data;
}

export async function getMessages(topicId: string) {
  const res = await apiRequest(`/api/v1/chat/topics/${topicId}/messages/`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}
