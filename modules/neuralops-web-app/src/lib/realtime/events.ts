// Typed contract for the events nucleus publishes on topic-{id} channels.
// Field quirks below are verified against server source — do not "clean up":
//  - user_typing carries `avatar`; every other event uses `sender_avatar`.
//  - swarm-relayed events arrive null-padded (all keys present, most null).
//  - swarm_transition REUSES the currently-streaming message's id.

export interface WireMessage {
  id: string;
  type: "message";
  message_type?: string | null;
  content: string;
  render_as?: string | null;
  output_type?: string | null;
  sender_name?: string | null;
  sender_id?: string | null;
  sender_avatar?: string | null;
  sender_type: string;
  persona_id?: string | null;
  sequence: number;
  created_at: string;
}

export type ChatEvent =
  | { kind: "message"; message: WireMessage }
  | { kind: "typing"; userId: string; name: string; avatar: string | null }
  | { kind: "start"; id: string; senderId?: string; senderName?: string; senderAvatar?: string; personaId?: string; sequence?: number; createdAt?: string }
  | { kind: "delta"; id: string; delta: string }
  | { kind: "done"; id: string; content?: string; outputType?: string; renderAs?: string }
  | { kind: "error"; id: string; content?: string }
  | { kind: "transition"; streamId: string; content: string; transitionType?: string; fromPersona?: string; toPersona?: string }
  // What the persona is doing right now (a tool call). `label` is the server's
  // wording — the client renders it verbatim and keeps no tool vocabulary.
  | { kind: "activity"; id: string; tool: string; label: string };

type Raw = Record<string, unknown>;
const str = (v: unknown): string | undefined => (typeof v === "string" && v.length > 0 ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);

export function parseEvent(raw: unknown): ChatEvent | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Raw;
  const type = str(r.type);
  const id = str(r.id);
  if (!type || !id) return null;

  switch (type) {
    case "message":
      if (typeof r.content !== "string" || typeof r.sequence !== "number") return null;
      return { kind: "message", message: r as unknown as WireMessage };
    case "user_typing":
      return { kind: "typing", userId: id, name: str(r.name) ?? "Someone", avatar: str(r.avatar) ?? null };
    case "message_start":
      return {
        kind: "start",
        id,
        senderId: str(r.sender_id),
        senderName: str(r.sender_name),
        senderAvatar: str(r.sender_avatar),
        personaId: str(r.persona_id),
        sequence: num(r.sequence),
        createdAt: str(r.created_at),
      };
    case "tool_activity": {
      const label = str(r.label);
      return label ? { kind: "activity", id, tool: str(r.tool) ?? "", label } : null;
    }
    case "message_delta":
      return { kind: "delta", id, delta: typeof r.delta === "string" ? r.delta : "" };
    case "message_done":
      return { kind: "done", id, content: str(r.content), outputType: str(r.output_type), renderAs: str(r.render_as) };
    case "message_error":
      return { kind: "error", id, content: str(r.content) };
    case "swarm_transition": {
      const meta = (typeof r.metadata === "object" && r.metadata !== null ? r.metadata : {}) as Raw;
      return {
        kind: "transition",
        streamId: id,
        content: str(r.content) ?? "",
        transitionType: str(meta.transition_type),
        fromPersona: str(meta.from_persona),
        toPersona: str(meta.to_persona),
      };
    }
    default:
      return null; // unknown event types are ignored by design
  }
}
