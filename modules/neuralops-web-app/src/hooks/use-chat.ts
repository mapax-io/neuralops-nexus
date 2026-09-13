"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { listMessages, sendMessage } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import { renameTopic } from "@/lib/api/workspace";
import { markdownToPlain } from "@/lib/markdown";
import { parseEvent, type ChatEvent, type MentionRefusal, type WireMessage } from "@/lib/realtime/events";
import {
  applyEvent,
  applyHistory,
  attachRefusals,
  expireTyping,
  initialChatState,
  markStalled,
  orderedMessages,
  type ChatState,
} from "@/lib/realtime/message-store";
import { onConnectionStatus, subscribeTopic, type ConnectionStatus } from "@/lib/realtime/centrifugo";
import { useConnectionStore } from "@/stores/connection.store";

// One short 880Hz sine chime, WebAudio only (no asset). Fails silently on
// autoplay restrictions — a missed chime is never worth an error.
let chimeCtx: AudioContext | null = null;
function playChime() {
  try {
    chimeCtx = chimeCtx ?? new AudioContext();
    const osc = chimeCtx.createOscillator();
    const gain = chimeCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.06, chimeCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, chimeCtx.currentTime + 0.25);
    osc.connect(gain).connect(chimeCtx.destination);
    osc.start();
    osc.stop(chimeCtx.currentTime + 0.25);
  } catch {
    /* audio blocked — fine */
  }
}

type Action =
  | { t: "history"; wire: WireMessage[]; force?: boolean }
  | { t: "event"; ev: ChatEvent; now: number; self: string | null }
  | { t: "tick"; now: number }
  | { t: "local"; wire: WireMessage; now: number; refusals?: MentionRefusal[] }
  | { t: "reset" };

function reducer(state: ChatState, a: Action): ChatState {
  switch (a.t) {
    case "history":
      return applyHistory(state, a.wire, a.force);
    case "event":
      // Persona progress is conveyed by the streaming message bubble itself (an
      // in-bubble "Thinking…" cue before the first token, then the streaming
      // caret; message_start→done). We deliberately do NOT also raise a floating
      // "is thinking" bar for personas: it duplicated that bubble and overlapped
      // it at the bottom of the list. The floating TypingBar is humans-only (they
      // have no bubble until they send).
      return applyEvent(state, a.ev, a.now, a.self);
    case "tick":
      return markStalled(expireTyping(state, a.now), a.now);
    case "local": {
      const next = applyEvent(state, { kind: "message", message: a.wire }, a.now, null);
      return a.refusals?.length ? attachRefusals(next, a.wire.id, a.refusals) : next;
    }
    case "reset":
      return initialChatState();
  }
}

const AUTO_TITLE_RE = /^chat#\d+$/;

// Derive a chat title from a message: plain-text projection, mention tokens
// and OUTPUT DIRECTIVES stripped. Only known directive words — a blind /\w+
// strip mangled ordinary text ("and/or", "https://…").
const DIRECTIVE_WORDS = /(^|\s)\/(chart|table|mermaid|plan|code|terminal|web|html|text|swarm|session)\b/gi;
function deriveTitle(content: string): string {
  return markdownToPlain(content).replace(/@[\w]+/g, "").replace(DIRECTIVE_WORDS, " ").replace(/\s+/g, " ").trim().slice(0, 60);
}

export function useChat(projectId?: string, channelId?: string, topicId?: string, topicTitle?: string) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const hasToken = !!token;
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(reducer, undefined, initialChatState);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadErrorStatus, setLoadErrorStatus] = useState<number | null>(null);
  const [connection, setConnection] = useState<ConnectionStatus>("disconnected");
  const renamedRef = useRef<string | null>(null);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const titleRef = useRef(topicTitle);
  useEffect(() => {
    titleRef.current = topicTitle;
  }, [topicTitle]);

  // History + live subscription — strictly for the open topic only.
  useEffect(() => {
    if (!serverUrl || !token || !projectId || !channelId || !topicId) return;
    let alive = true;
    let settled = false;
    dispatch({ t: "reset" });
    // Deferred via rAF (no setState directly in the effect body) — but the
    // fetch can win the race (fast LAN server, or a hidden tab where rAFs
    // don't fire until visibility): once settled, the boot reset must not
    // flip `loading` back on, or the chat blanks out permanently.
    const boot = requestAnimationFrame(() => {
      if (settled) return;
      setLoading(true);
      setLoadError(null);
      setLoadErrorStatus(null);
    });

    listMessages(projectId, channelId, topicId)
      .then((wire) => alive && dispatch({ t: "history", wire }))
      .catch((e) => {
        if (!alive) return;
        setLoadError(e instanceof Error ? e.message : "Could not load messages.");
        setLoadErrorStatus(e instanceof ApiError ? e.status : null);
      })
      .finally(() => {
        settled = true;
        if (alive) setLoading(false);
      });

    const unsubscribe = subscribeTopic(serverUrl, topicId, (data) => {
      const ev = parseEvent(data);
      if (!ev) return;
      // Self-comparison uses the SERVER's user id (typing events carry the
      // nucleus id, not the identity provider's) — read fresh, not from a closure.
      const { connection } = useConnectionStore.getState();
      // Typing events carry the NUCLEUS id — a Supabase-id fallback can never
      // match and would let your own typing echo back.
      const selfId = connection?.nucleusUserId ?? null;
      // Soft chime on incoming activity (parity with the classic app): a
      // human message from someone else, or a persona starting to answer.
      if ((ev.kind === "message" && ev.message.sender_id !== selfId) || ev.kind === "start") playChime();
      dispatch({ t: "event", ev, now: Date.now(), self: selfId });
      // Topic auto-rename: only while the title is still auto-generated
      // (chat#N), after the first completed AI reply — derived from the
      // triggering human message (mention tokens stripped, 60 chars).
      if (ev.kind === "done" && renamedRef.current !== topicId && titleRef.current && AUTO_TITLE_RE.test(titleRef.current)) {
        const msgs = orderedMessages(stateRef.current);
        const trigger = [...msgs].reverse().find((m) => m.senderType === "human" && !m.isSystem);
        const title = trigger ? deriveTitle(trigger.content) : undefined;
        if (title && title !== titleRef.current) {
          // Latch only on an ATTEMPT, un-latch on failure — a transient error
          // (or a scheduled persona firing first) must not block the rename.
          renamedRef.current = topicId;
          renameTopic(projectId, channelId, topicId, title)
            .then(() => queryClient.invalidateQueries({ queryKey: ["topics"] }))
            .catch(() => {
              renamedRef.current = null;
            });
        }
      }
    });

    const timer = setInterval(() => dispatch({ t: "tick", now: Date.now() }), 4_000);
    // Reconcile-from-history runs only on a RE-connect. The status listener
    // fires synchronously with the current status at registration (usually
    // "connecting" on a fresh page), which must not count as an outage or
    // every page load would double-fetch history.
    let everConnected = false;
    let wasDown = false;
    const offStatus = onConnectionStatus((s) => {
      setConnection(s);
      if (s !== "connected") {
        if (everConnected) wasDown = true;
        return;
      }
      if (everConnected && wasDown) {
        // Events published while offline are gone — reconcile from history.
        listMessages(projectId, channelId, topicId)
          .then((wire) => alive && dispatch({ t: "history", wire, force: true }))
          .catch(() => undefined);
      }
      everConnected = true;
      wasDown = false;
    });
    return () => {
      alive = false;
      cancelAnimationFrame(boot);
      unsubscribe();
      clearInterval(timer);
      offStatus();
    };
    // `token` is only an existence gate (apiJson reads it fresh) — depending
    // on its VALUE would tear down the live chat on every hourly refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hasToken gate + stable refs/queryClient
  }, [serverUrl, hasToken, projectId, channelId, topicId]);

  const send = useCallback(
    async (content: string) => {
      if (!projectId || !channelId || !topicId) return;
      const out = await sendMessage(projectId, channelId, topicId, content).catch((e) => {
        toast.error(e instanceof Error ? e.message : "Message failed to send.");
        throw e;
      });
      dispatch({ t: "local", wire: out.message, now: Date.now(), refusals: out.refusals ?? [] });
      // The note stays under the message; the toast is for eyes that had
      // already moved on.
      for (const r of out.refusals ?? []) toast.warning(`@${r.name} didn't answer`, { description: r.message });
      // Auto-generated chats take their name from the FIRST message —
      // immediately, not only after an AI reply.
      if (renamedRef.current !== topicId && titleRef.current && AUTO_TITLE_RE.test(titleRef.current)) {
        const title = deriveTitle(content);
        // Latch only on an actual ATTEMPT — a bare "@mention" first message
        // yields an empty title, and latching then would disable auto-rename
        // for the topic's whole life.
        if (title && title !== titleRef.current) {
          renamedRef.current = topicId;
          renameTopic(projectId, channelId, topicId, title)
            .then(() => queryClient.invalidateQueries({ queryKey: ["topics"] }))
            .catch(() => {
              renamedRef.current = null; // transient failure must not latch — retry on next send
            });
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs + stable queryClient
    [projectId, channelId, topicId],
  );

  const refetch = useCallback(() => {
    if (!projectId || !channelId || !topicId) return;
    // Retry must be able to LEAVE the error state — clearing the error only
    // on success, and saying so on another failure. A transient failure must
    // never latch the error screen.
    setLoading(true);
    listMessages(projectId, channelId, topicId)
      .then((wire) => {
        dispatch({ t: "history", wire });
        setLoadError(null);
        setLoadErrorStatus(null);
      })
      .catch((e) => {
        setLoadError(e instanceof Error ? e.message : "Could not load messages.");
        setLoadErrorStatus(e instanceof ApiError ? e.status : null);
        toast.error("Still can't load this chat — check the connection and retry.");
      })
      .finally(() => setLoading(false));
  }, [projectId, channelId, topicId]);

  const loadOlder = useCallback(async () => {
    if (!projectId || !channelId || !topicId) return 0;
    const oldest = orderedMessages(stateRef.current).find((m) => m.sequence !== null);
    if (!oldest?.sequence) return 0;
    const wire = await listMessages(projectId, channelId, topicId, oldest.sequence);
    dispatch({ t: "history", wire });
    return wire.length;
  }, [projectId, channelId, topicId]);

  // Memoized projections: fresh objects per STATE change only, not per parent
  // render — MessageItem's memo depends on these keeping their identity.
  const messages = useMemo(() => orderedMessages(state), [state]);
  const typing = useMemo(() => Object.values(state.typing), [state]);

  return {
    messages,
    totalLoaded: Object.keys(state.messages).length,
    transitions: state.transitions,
    typing,
    loading,
    loadError,
    loadErrorStatus,
    connection,
    send,
    refetch,
    loadOlder,
  };
}
