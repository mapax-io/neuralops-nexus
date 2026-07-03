import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { listMessages, sendMessage, type ApiMessage } from "@/services/chat.service";
import { useCentrifugo } from "./useCentrifugo";
import type { ChatMessage } from "@/components/chat/types";

// Map our API message shape → ChatMessage expected by MessageList/MessageItem
function toUiMessage(m: ApiMessage): ChatMessage {
  return {
    id: m.id,
    type: "text",
    content: m.content,
    sender: {
      id: m.sender_id,
      name: m.sender_name,
      type: "human",   // Phase 1: all messages are human
      avatar: null,
    },
    timestamp: m.created_at,
  };
}

export function useTopicMessages(
  projectId: string | null,
  channelId: string | null,
  topicId: string | null,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const { subscribe } = useCentrifugo();

  // Load history when topic changes
  useEffect(() => {
    if (!projectId || !channelId || !topicId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    listMessages(projectId, channelId, topicId)
      .then((msgs) => setMessages(msgs.map(toUiMessage)))
      .catch((err) => toast.error(err.message ?? "Failed to load messages"))
      .finally(() => setLoading(false));
  }, [projectId, channelId, topicId]);

  // Subscribe to Centrifugo for live messages
  useEffect(() => {
    if (!topicId) return;
    const channel = `topic:${topicId}`;

    const unsub = subscribe(channel, (data) => {
      const msg = data as ApiMessage;
      if (msg?.type === "message" && msg?.id) {
        setMessages((prev) => {
          // Deduplicate — sender may already have added optimistically
          if (prev.some((m) => m.id === msg.id)) return prev;
          return [...prev, toUiMessage(msg)];
        });
      }
    });

    return unsub;
  }, [topicId, subscribe]);

  const send = useCallback(
    async (content: string) => {
      if (!projectId || !channelId || !topicId) return;
      // No optimistic update — Centrifugo will deliver it back to us
      try {
        await sendMessage(projectId, channelId, topicId, content);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to send";
        toast.error(msg);
        throw err;
      }
    },
    [projectId, channelId, topicId],
  );

  return { messages, loading, send };
}
