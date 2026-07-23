import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
  listMessages,
  sendMessage,
  type ApiMessage,
} from "@/services/chat.service";
import { useCentrifugo } from "./useCentrifugo";
import { useAuthStore } from "@/store/auth.store";
import type { ChatMessage, MessageRenderType } from "@/components/chat/types";

// ---------------------------------------------------------------------------
// Beep
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
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Centrifugo event shapes
// ---------------------------------------------------------------------------
type HumanMessageEvent = ApiMessage & { type: "message" };

interface AiStartEvent {
  type: "message_start";
  id: string;
  sender_id: string;
  sender_name: string;
  sequence: number;
  created_at: string;
}
interface AiDeltaEvent {
  type: "message_delta";
  id: string;
  delta: string;
}
interface AiDoneEvent {
  type: "message_done";
  id: string;
  content?: string;
  output_type?: string;    // M7: e.g. "chart", "text"
  render_as?: string;      // M7: e.g. "html", "text", "code", "terminal"
}

type CentrifugoEvent =
  | HumanMessageEvent
  | AiStartEvent
  | AiDeltaEvent
  | AiDoneEvent;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map render_as string from the API → MessageRenderType used by the frontend.
 * Defaults to "text" for unknown values.
 */
function toRenderType(renderAs: string | undefined): MessageRenderType {
  switch (renderAs) {
    case "html":
    case "code":
    case "terminal":
    case "image":
    case "web":
      return renderAs;
    default:
      return "text";
  }
}

function toUiMessage(m: ApiMessage): ChatMessage {
  return {
    id: m.id,
    type: toRenderType(m.render_as),
    output_type: m.output_type,
    message_type: m.message_type,
    content: m.content,
    sender: {
      id: m.sender_id ?? "",
      name: m.sender_name ?? "",
      type: m.sender_type === "persona" ? "agent" : "human",
      avatar: null,
    },
    timestamp: m.created_at,
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useTopicMessages(
  projectId: string | null,
  channelId: string | null,
  topicId: string | null,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const { subscribe } = useCentrifugo();
  const currentUserId = useAuthStore((s) => s.userId);

  // Load history
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

  // Centrifugo subscription
  useEffect(() => {
    if (!topicId) return;
    const channel = `topic-${topicId}`;

    const unsub = subscribe(channel, (data) => {
      const event = data as CentrifugoEvent;

      if (!event?.type || !("id" in event)) return;

      if (event.type === "message") {
        // Human message from another user
        setMessages((prev) => {
          if (prev.some((m) => m.id === event.id)) return prev;
          if (event.sender_id !== currentUserId) playBeep();
          return [...prev, toUiMessage(event)];
        });

      } else if (event.type === "message_start") {
        // AI persona started responding — placeholder with streaming cursor
        playBeep();
        setMessages((prev) => {
          if (prev.some((m) => m.id === event.id)) return prev;
          return [
            ...prev,
            {
              id: event.id,
              type: "text",          // placeholder — updated on message_done
              output_type: "text",
              content: "",
              sender: {
                id: event.sender_id,
                name: event.sender_name,
                type: "agent",
                avatar: null,
              },
              timestamp: event.created_at,
              isStreaming: true,
            } satisfies ChatMessage,
          ];
        });

      } else if (event.type === "message_delta") {
        // Append streaming token
        setMessages((prev) =>
          prev.map((m) =>
            m.id === event.id
              ? { ...m, content: m.content + event.delta }
              : m,
          ),
        );

      } else if (event.type === "message_done") {
        // Streaming complete — replace content with clean version + set renderer
        const renderType = toRenderType(event.render_as);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === event.id
              ? {
                  ...m,
                  isStreaming: false,
                  type: renderType,
                  output_type: event.output_type ?? "text",
                  // Replace with nexus-ai's clean content (markers stripped)
                  content: event.content !== undefined ? event.content : m.content,
                }
              : m,
          ),
        );
      }
    });

    return unsub;
  }, [topicId, subscribe, currentUserId]);

  // Polling fallback — catches messages from other users when WebSocket is slow
  useEffect(() => {
    if (!projectId || !channelId || !topicId) return;
    const poll = async () => {
      try {
        const msgs = await listMessages(projectId, channelId, topicId);
        setMessages((prev) => {
          const existingIds = new Set(prev.map((m) => m.id));
          const fresh = msgs.filter((m) => !existingIds.has(m.id));
          if (fresh.length === 0) return prev;
          if (fresh.some((m) => m.sender_id !== currentUserId)) playBeep();
          const merged = [...prev, ...fresh.map(toUiMessage)];
          merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
          return merged;
        });
      } catch { /* silent */ }
    };
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [projectId, channelId, topicId, currentUserId]);

  const send = useCallback(
    async (content: string) => {
      if (!projectId || !channelId || !topicId) return;

      try {
        const { message } = await sendMessage(projectId, channelId, topicId, content);
        setMessages((prev) => {
          if (prev.some((m) => m.id === message.id)) return prev;
          return [...prev, toUiMessage(message)];
        });
      } catch (err: unknown) {
        console.error("[useChat] sendMessage failed:", err);
        const msg = err instanceof Error ? err.message : "Failed to send";
        toast.error(msg);
        throw err;
      }
    },
    [projectId, channelId, topicId],
  );

  return { messages, loading, send };
}
