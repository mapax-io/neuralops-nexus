import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { listMessages, sendMessage, type ApiMessage } from "@/services/chat.service";
import { useCentrifugo } from "./useCentrifugo";
import { useAuthStore } from "@/store/auth.store";
import type { ChatMessage } from "@/components/chat/types";

// ---------------------------------------------------------------------------
// Beep — plays a short 880 Hz "ding" via Web Audio API when an incoming
// message arrives from another user. No external file needed.
// ---------------------------------------------------------------------------
function playBeep(): void {
  try {
    const ctx = new AudioContext();
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);

    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.25);
    osc.onended = () => ctx.close();
  } catch {
    // Browsers may block AudioContext until user interaction — ignore silently
  }
}

// ---------------------------------------------------------------------------
// Map API message shape → ChatMessage expected by MessageList/MessageItem
// ---------------------------------------------------------------------------
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
  const currentUserId = useAuthStore((s) => s.userId);

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
          // Beep only for messages from other users
          if (msg.sender_id !== currentUserId) {
            playBeep();
          }
          return [...prev, toUiMessage(msg)];
        });
      }
    });

    return unsub;
  }, [topicId, subscribe, currentUserId]);

  // Polling fallback — catches messages missed during WebSocket gaps.
  // Centrifugo memory engine has no history: if the WS drops for even a
  // moment, publications in that window are lost. Polling every 3 s ensures
  // eventual delivery regardless of connection state.
  useEffect(() => {
    if (!projectId || !channelId || !topicId) return;

    const poll = async () => {
      try {
        const msgs = await listMessages(projectId, channelId, topicId);
        setMessages((prev) => {
          const existingIds = new Set(prev.map((m) => m.id));
          const fresh = msgs.filter((m) => !existingIds.has(m.id));
          if (fresh.length === 0) return prev;
          // Beep if any freshly-polled message is from someone else
          if (fresh.some((m) => m.sender_id !== currentUserId)) {
            playBeep();
          }
          const merged = [...prev, ...fresh.map(toUiMessage)];
          merged.sort(
            (a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
          );
          return merged;
        });
      } catch {
        // silent — don't spam toasts on poll failure
      }
    };

    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [projectId, channelId, topicId, currentUserId]);

  const send = useCallback(
    async (content: string) => {
      if (!projectId || !channelId || !topicId) return;
      try {
        const { message } = await sendMessage(projectId, channelId, topicId, content);
        // Add to local state immediately so the sender sees their own message
        // without waiting for Centrifugo. The dedup check in the subscription
        // handler prevents a duplicate when the WS echo arrives.
        setMessages((prev) => {
          if (prev.some((m) => m.id === message.id)) return prev;
          return [...prev, toUiMessage(message)];
        });
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
