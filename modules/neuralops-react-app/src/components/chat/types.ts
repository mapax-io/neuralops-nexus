export interface MessageSender {
  id: string;
  name: string;
  type: "human" | "persona" | "agent";
  avatar: string | null;
}

export interface ChatMessage {
  id: string;
  type: "text" | "code" | "terminal" | "chart" | "form" | "image" | "web";
  content: string;
  language?: string;
  metadata?: Record<string, unknown>;
  sender: MessageSender;
  timestamp: string;
  isStreaming?: boolean;
}

export interface TypingActor {
  id: string;
  name: string;
  type: "human" | "persona" | "agent";
  avatar: string | null;
}
