import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
  listMessages,
  sendMessage,
  triggerAiSpike,        // ⚠️ SPIKE — remove when nexus-ai is wired up
  type ApiMessage,
} from "@/services/chat.service";
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
// Centrifugo event shapes
// ---------------------------------------------------------------------------

// Human message (existing)
type HumanMessageEvent = ApiMessage & { type: "message" };

// ⚠️ SPIKE events — these shapes are permanent (nexus-ai will use them too)
interface AiStartEvent {
  type: "message_start";
  id: string;
  sender_id: string;
  sender_name: string;
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
}

type CentrifugoEvent =
  | HumanMessageEvent
  | AiStartEvent
  | AiDeltaEvent
  | AiDoneEvent;

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

// ⚠️ SPIKE trigger — prefix the user types to invoke the AI
const AI_TEST_PREFIX = "/ai-test ";

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

  // Subscribe to Centrifugo for live messages + AI streaming events
  useEffect(() => {
    if (!topicId) return;
    const channel = `topic:${topicId}`;

    const unsub = subscribe(channel, (data) => {
      const event = data as CentrifugoEvent;
      if (!event?.type || !event?.id) return;

      if (event.type === "message") {
        // ── Human message ────────────────────────────────────────────────
        setMessages((prev) => {
          if (prev.some((m) => m.id === event.id)) return prev;
          if (event.sender_id !== currentUserId) playBeep();
          return [...prev, toUiMessage(event)];
        });

      } else if (event.type === "message_start") {
        // ── AI message bubble appears with blinking cursor ───────────────
        playBeep();
        setMessages((prev) => {
          if (prev.some((m) => m.id === event.id)) return prev;
          return [
            ...prev,
            {
              id: event.id,
              type: "text",
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
        // ── Token arrives — append to streaming message ──────────────────
        setMessages((prev) =>
          prev.map((m) =>
            m.id === event.id
              ? { ...m, content: m.content + event.delta }
              : m,
          ),
        );

      } else if (event.type === "message_done") {
        // ── Stream finished — remove blinking cursor ─────────────────────
        setMessages((prev) =>
          prev.map((m) =>
            m.id === event.id ? { ...m, isStreaming: false } : m,
          ),
        );
      }
    });

    return unsub;
  }, [topicId, subscribe, currentUserId]);

  // Polling fallback — catches messages missed during WebSocket gaps.
  useEffect(() => {
    if (!projectId || !channelId || !topicId) return;

    const poll = async () => {
      try {
        const msgs = await listMessages(projectId, channelId, topicId);
        setMessages((prev) => {
          const existingIds = new Set(prev.map((m) => m.id));
          const fresh = msgs.filter((m) => !existingIds.has(m.id));
          if (fresh.length === 0) return prev;
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

      // ⚠️ SPIKE — detect /ai-test prefix and route to spike endpoint
      // Remove this block when nexus-ai @mention detection is implemented.
      if (content.startsWith(AI_TEST_PREFIX)) {
        const query = content.slice(AI_TEST_PREFIX.length).trim();
        if (!query) return;
        try {
          await triggerAiSpike(projectId, channelId, topicId, query);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : "AI spike failed";
          toast.error(msg);
        }
        return;
      }

      // Normal human message flow
      try {
        const { message } = await sendMessage(projectId, channelId, topicId, content);
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
