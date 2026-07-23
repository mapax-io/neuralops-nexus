import { apiJson } from "./api-client";

// Shape returned by GET + POST /messages/
export interface ApiMessage {
  id: string;
  type: string;
  message_type?: string;
  content: string;
  render_as?: string;    // M7: "text" | "code" | "html" | "terminal"
  output_type?: string;  // M7: "text" | "chart" | "table" | "diagram" | ...
  sender_name: string;
  sender_id: string | null;
  sender_type: string;
  sequence: number;
  created_at: string;
}

export interface SendMessageResponse {
  message: ApiMessage;
  channel: string;   // Centrifugo channel: "topic-{topic_id}"
}

export async function listMessages(
  projectId: string,
  channelId: string,
  topicId: string,
): Promise<ApiMessage[]> {
  return apiJson<ApiMessage[]>(
    `/api/v1/projects/${projectId}/channels/${channelId}/topics/${topicId}/messages/`,
  );
}

export async function sendMessage(
  projectId: string,
  channelId: string,
  topicId: string,
  content: string,
): Promise<SendMessageResponse> {
  return apiJson<SendMessageResponse>(
    `/api/v1/projects/${projectId}/channels/${channelId}/topics/${topicId}/messages/`,
    {
      method: "POST",
      body: JSON.stringify({ content }),
    },
  );
}
