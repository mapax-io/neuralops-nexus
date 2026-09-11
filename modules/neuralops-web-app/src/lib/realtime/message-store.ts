import type { ChatEvent, WireMessage } from "./events";

// Pure reducer for a topic's live message state. Encodes every server quirk:
// start-events may arrive twice per id (merge, never clobber), deltas can
// precede their start, multiple dones arrive per send (swarm hops), swarm
// failures emit NO terminal event (stall detection), transitions must not be
// keyed by their id (it collides with the streaming message).

export interface UiMessage {
  id: string;
  content: string;
  renderAs: string;
  outputType: string;
  senderName: string | null;
  senderId: string | null;
  senderAvatar: string | null;
  senderType: string;
  personaId: string | null;
  sequence: number | null;
  createdAt: string | null;
  isSystem: boolean;
  isStreaming: boolean;
  isError: boolean;
  isStalled: boolean;
  lastActivity: number;
  /** Server-supplied wording for the tool in flight, shown while streaming. */
  activity?: string | null;
}

export interface TransitionItem {
  key: string;
  content: string;
  transitionType?: string;
  fromPersona?: string;
  toPersona?: string;
  afterSortKey: number;
}

export interface TypingActor {
  key: string;
  name: string;
  avatar: string | null;
  kind: "human" | "persona";
  expiresAt: number;
}

export interface ChatState {
  messages: Record<string, UiMessage>;
  transitions: TransitionItem[];
  typing: Record<string, TypingActor>;
  transitionSeq: number;
}

export const HUMAN_TYPING_TTL_MS = 4_000;
export const STREAM_STALL_MS = 90_000;

export const initialChatState = (): ChatState => ({ messages: {}, transitions: [], typing: {}, transitionSeq: 0 });

function fromWire(m: WireMessage): UiMessage {
  return {
    id: m.id,
    content: m.content,
    renderAs: m.render_as || "text",
    outputType: m.output_type || "text",
    senderName: m.sender_name ?? null,
    senderId: m.sender_id ?? null,
    senderAvatar: m.sender_avatar ?? null,
    senderType: m.sender_type,
    personaId: m.persona_id ?? null,
    sequence: m.sequence,
    createdAt: m.created_at,
    isSystem: m.sender_type === "system" || m.message_type === "system",
    isStreaming: false,
    isError: false,
    isStalled: false,
    lastActivity: 0,
  };
}

export function sortKey(m: UiMessage): number {
  return m.sequence ?? (m.createdAt ? new Date(m.createdAt).getTime() / 1e10 + 1e6 : Number.MAX_SAFE_INTEGER);
}

const bySortKey = (a: UiMessage, b: UiMessage) =>
  sortKey(a) - sortKey(b) || (a.createdAt ?? "").localeCompare(b.createdAt ?? "") || a.id.localeCompare(b.id);

export function orderedMessages(state: ChatState): UiMessage[] {
  return Object.values(state.messages).sort(bySortKey);
}

export function applyHistory(state: ChatState, wire: WireMessage[], force = false): ChatState {
  const messages = { ...state.messages };
  for (const m of wire) {
    // History wins over any placeholder, but never downgrades a live stream —
    // EXCEPT on reconnect reconciliation (force): events published while
    // offline are gone, so the server snapshot is the only source of the
    // final message. Tradeoff: a stream still live across the gap re-appends
    // its next deltas onto the snapshot; rarer and self-corrects on done.
    const existing = messages[m.id];
    if (existing?.isStreaming && !force) continue;
    messages[m.id] = fromWire(m);
  }
  return { ...state, messages };
}

export function applyEvent(state: ChatState, ev: ChatEvent, now: number, selfUserId?: string | null): ChatState {
  switch (ev.kind) {
    case "message": {
      const msg = fromWire(ev.message);
      const typing = { ...state.typing };
      if (msg.senderId) delete typing[`human:${msg.senderId}`];
      return { ...state, typing, messages: { ...state.messages, [msg.id]: { ...state.messages[msg.id], ...msg } } };
    }

    case "typing": {
      if (selfUserId && ev.userId === selfUserId) return state; // own echo — server does not exclude the sender
      const key = `human:${ev.userId}`;
      return { ...state, typing: { ...state.typing, [key]: { key, name: ev.name, avatar: ev.avatar, kind: "human", expiresAt: now + HUMAN_TYPING_TTL_MS } } };
    }

    case "start": {
      const existing = state.messages[ev.id];
      const merged: UiMessage = {
        id: ev.id,
        content: existing?.content ?? "",
        renderAs: existing?.renderAs ?? "text",
        outputType: existing?.outputType ?? "text",
        // Merge: the swarm relay re-emits hop-1's start WITHOUT sender fields.
        senderName: ev.senderName ?? existing?.senderName ?? null,
        senderId: ev.senderId ?? existing?.senderId ?? null,
        senderAvatar: ev.senderAvatar ?? existing?.senderAvatar ?? null,
        senderType: existing?.senderType ?? "persona",
        personaId: ev.personaId ?? existing?.personaId ?? null,
        sequence: ev.sequence ?? existing?.sequence ?? null,
        createdAt: ev.createdAt ?? existing?.createdAt ?? null,
        isSystem: false,
        isStreaming: existing?.isStreaming ?? true,
        isError: existing?.isError ?? false,
        isStalled: false,
        lastActivity: now,
      };
      if (!existing) merged.isStreaming = true;
      return { ...state, messages: { ...state.messages, [ev.id]: merged } };
    }

    // A tool call started. Counts as activity (so stall detection holds off)
    // and replaces the "Thinking" wording until the next token arrives.
    case "activity": {
      const existing = state.messages[ev.id];
      if (!existing) return state;
      return {
        ...state,
        messages: {
          ...state.messages,
          [ev.id]: { ...existing, activity: ev.label, isStalled: false, lastActivity: now },
        },
      };
    }

    case "delta": {
      const existing = state.messages[ev.id];
      const base: UiMessage = existing ?? {
        // Delta before start: materialize a minimal streaming bubble.
        id: ev.id, content: "", renderAs: "text", outputType: "text",
        senderName: null, senderId: null, senderAvatar: null, senderType: "persona",
        personaId: null, sequence: null, createdAt: null,
        isSystem: false, isStreaming: true, isError: false, isStalled: false, lastActivity: now,
      };
      return {
        ...state,
        messages: { ...state.messages, [ev.id]: { ...base, content: base.content + ev.delta, isStreaming: true, isStalled: false, activity: null, lastActivity: now } },
      };
    }

    case "done": {
      const existing = state.messages[ev.id];
      const target: UiMessage = existing ?? {
        id: ev.id, content: "", renderAs: "text", outputType: "text",
        senderName: null, senderId: null, senderAvatar: null, senderType: "persona",
        personaId: null, sequence: null, createdAt: null,
        isSystem: false, isStreaming: false, isError: false, isStalled: false, lastActivity: now,
      };
      return {
        ...state,
        messages: {
          ...state.messages,
          [ev.id]: {
            ...target,
            content: ev.content ?? target.content,
            renderAs: ev.renderAs ?? target.renderAs,
            outputType: ev.outputType ?? target.outputType,
            isStreaming: false,
            isStalled: false,
            lastActivity: now,
          },
        },
      };
    }

    case "error": {
      const existing = state.messages[ev.id];
      const target: UiMessage = existing ?? {
        id: ev.id, content: "", renderAs: "text", outputType: "text",
        senderName: null, senderId: null, senderAvatar: null, senderType: "persona",
        personaId: null, sequence: null, createdAt: null,
        isSystem: false, isStreaming: false, isError: true, isStalled: false, lastActivity: now,
      };
      return {
        ...state,
        messages: {
          ...state.messages,
          [ev.id]: { ...target, content: ev.content ?? target.content ?? "Something went wrong generating this response.", isStreaming: false, isError: true, lastActivity: now },
        },
      };
    }

    case "transition": {
      // Never key by ev.streamId — it collides with the live message. Anchor
      // the notice after the stream's current position.
      const anchor = state.messages[ev.streamId];
      const seq = state.transitionSeq + 1;
      return {
        ...state,
        transitionSeq: seq,
        transitions: [
          ...state.transitions,
          {
            key: `transition-${seq}`,
            content: ev.content,
            transitionType: ev.transitionType,
            fromPersona: ev.fromPersona,
            toPersona: ev.toPersona,
            afterSortKey: anchor ? sortKey(anchor) + seq / 1e6 : Number.MAX_SAFE_INTEGER,
          },
        ],
      };
    }
  }
}

export function expireTyping(state: ChatState, now: number): ChatState {
  const alive = Object.fromEntries(Object.entries(state.typing).filter(([, a]) => a.expiresAt > now));
  return Object.keys(alive).length === Object.keys(state.typing).length ? state : { ...state, typing: alive };
}

// The swarm path emits no terminal event on failure: mark long-quiet streams.
export function markStalled(state: ChatState, now: number): ChatState {
  let changed = false;
  const messages = { ...state.messages };
  for (const [id, m] of Object.entries(messages)) {
    if (m.isStreaming && !m.isStalled && now - m.lastActivity > STREAM_STALL_MS) {
      messages[id] = { ...m, isStalled: true };
      changed = true;
    }
  }
  return changed ? { ...state, messages } : state;
}

