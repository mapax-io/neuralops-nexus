import { describe, expect, it } from "vitest";
import { parseEvent } from "./events";
import {
  applyEvent,
  applyHistory,
  expireTyping,
  initialChatState,
  markStalled,
  orderedMessages,
  STREAM_STALL_MS,
  type ChatState,
} from "./message-store";

const NOW = 1_000_000;

function ev(state: ChatState, raw: unknown, now = NOW, self?: string) {
  const parsed = parseEvent(raw);
  expect(parsed).not.toBeNull();
  return applyEvent(state, parsed!, now, self);
}

const wireMsg = (id: string, seq: number, over: Record<string, unknown> = {}) => ({
  id, type: "message" as const, message_type: "text", content: `m${seq}`, render_as: "text", output_type: "text",
  sender_name: "Waqas", sender_id: "u1", sender_avatar: "/media/a.png", sender_type: "human",
  persona_id: null, sequence: seq, created_at: "2026-08-29T10:00:00Z", ...over,
});

describe("event parsing", () => {
  it("parses user_typing with its odd `avatar` key", () => {
    const p = parseEvent({ type: "user_typing", id: "u2", name: "Sara", avatar: "/media/s.png" });
    expect(p).toEqual({ kind: "typing", userId: "u2", name: "Sara", avatar: "/media/s.png" });
  });
  it("tolerates null-padded swarm events", () => {
    const p = parseEvent({ type: "message_done", id: "x", created_at: null, persona_id: null, delta: null, content: "hi", output_type: "text", render_as: "text", embed_description: null, metadata: null, error: null });
    expect(p).toEqual({ kind: "done", id: "x", content: "hi", outputType: "text", renderAs: "text" });
  });
  it("ignores unknown event types", () => {
    expect(parseEvent({ type: "tool_call_start", id: "x" })).toBeNull();
  });
});

describe("message store", () => {
  it("streams the normal lifecycle: start → deltas → done", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "a1", sender_id: "p1", sender_name: "Layla", sender_avatar: null, sequence: 5, created_at: "2026-08-29T10:00:01Z" });
    expect(s.messages.a1.isStreaming).toBe(true);
    s = ev(s, { type: "message_delta", id: "a1", delta: "Hel" });
    s = ev(s, { type: "message_delta", id: "a1", delta: "lo" });
    expect(s.messages.a1.content).toBe("Hello");
    s = ev(s, { type: "message_done", id: "a1", content: "Hello!", output_type: "text", render_as: "text" });
    expect(s.messages.a1).toMatchObject({ content: "Hello!", isStreaming: false, isError: false });
  });

  it("merges a duplicate start without losing sender fields (swarm hop-1 quirk)", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "a1", sender_id: "p1", sender_name: "Layla", sender_avatar: "/x.png", sequence: 5, created_at: "t" });
    // relayed copy: same id, sender fields absent, null-padded
    s = ev(s, { type: "message_start", id: "a1", sender_name: null, sender_avatar: null, persona_id: "per-1", created_at: "t2" });
    expect(s.messages.a1.senderName).toBe("Layla");
    expect(s.messages.a1.senderAvatar).toBe("/x.png");
    expect(s.messages.a1.personaId).toBe("per-1");
    expect(Object.keys(s.messages)).toHaveLength(1);
  });

  it("materializes on delta-before-start and done-without-delta", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_delta", id: "b1", delta: "hi" });
    expect(s.messages.b1).toMatchObject({ content: "hi", isStreaming: true });
    s = ev(s, { type: "message_done", id: "c1", content: "full", render_as: "code", output_type: "code" });
    expect(s.messages.c1).toMatchObject({ content: "full", renderAs: "code", isStreaming: false });
  });

  it("tolerates multiple done events per send (swarm hops) idempotently", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_done", id: "h1", content: "hop one", render_as: "text", output_type: "text" });
    s = ev(s, { type: "message_done", id: "h1", content: "hop one", render_as: "text", output_type: "text" });
    s = ev(s, { type: "message_start", id: "h2", sequence: 9 });
    s = ev(s, { type: "message_done", id: "h2", content: "hop two", render_as: "text", output_type: "text" });
    expect(Object.keys(s.messages)).toHaveLength(2);
    expect(s.messages.h2.content).toBe("hop two");
  });

  it("keeps transitions on their own keys — never clobbering the colliding message id", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "m1", sequence: 3 });
    s = ev(s, { type: "message_delta", id: "m1", delta: "working…" });
    s = ev(s, { type: "swarm_transition", id: "m1", content: "Delegating task to @Dev...", metadata: { transition_type: "delegation", from_persona: "Layla", to_persona: "Dev" } });
    expect(s.messages.m1.content).toBe("working…"); // untouched
    expect(s.transitions).toHaveLength(1);
    expect(s.transitions[0]).toMatchObject({ transitionType: "delegation", fromPersona: "Layla", toPersona: "Dev" });
    expect(s.transitions[0].key).not.toBe("m1");
  });

  it("filters own typing echo and expires actors", () => {
    let s = initialChatState();
    s = ev(s, { type: "user_typing", id: "me", name: "Me", avatar: null }, NOW, "me");
    expect(Object.keys(s.typing)).toHaveLength(0);
    s = ev(s, { type: "user_typing", id: "u2", name: "Sara", avatar: null }, NOW, "me");
    expect(s.typing["human:u2"].name).toBe("Sara");
    s = expireTyping(s, NOW + 5_000);
    expect(Object.keys(s.typing)).toHaveLength(0);
  });

  it("clears a sender's typing actor when their message lands", () => {
    let s = initialChatState();
    s = ev(s, { type: "user_typing", id: "u1", name: "Waqas", avatar: null }, NOW, "me");
    s = ev(s, wireMsg("w1", 7), NOW, "me");
    expect(Object.keys(s.typing)).toHaveLength(0);
    expect(s.messages.w1.content).toBe("m7");
  });

  it("marks silent streams stalled (swarm has no terminal error event)", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "s1", sequence: 1 }, NOW);
    s = markStalled(s, NOW + STREAM_STALL_MS - 1);
    expect(s.messages.s1.isStalled).toBe(false);
    s = markStalled(s, NOW + STREAM_STALL_MS + 1);
    expect(s.messages.s1.isStalled).toBe(true);
    // a late delta recovers it
    s = ev(s, { type: "message_delta", id: "s1", delta: "…back" }, NOW + STREAM_STALL_MS + 2);
    expect(s.messages.s1.isStalled).toBe(false);
  });

  it("orders by sequence with history merge, and history never downgrades a live stream", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "live", sequence: 10 });
    s = ev(s, { type: "message_delta", id: "live", delta: "streaming" });
    s = applyHistory(s, [wireMsg("w1", 2), wireMsg("w2", 4), { ...wireMsg("live", 10), content: "stale snapshot" } as never]);
    expect(s.messages.live.content).toBe("streaming");
    expect(orderedMessages(s).map((m) => m.id)).toEqual(["w1", "w2", "live"]);
  });

  it("marks error messages and keeps them final", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "e1", sequence: 2 });
    s = ev(s, { type: "message_error", id: "e1", content: "Something went wrong generating this response." });
    expect(s.messages.e1).toMatchObject({ isError: true, isStreaming: false });
  });
});

// The AI worker's single-persona path (upstream #101) stopped sending
// output_type on message_done; nucleus fills "text" while render_as still
// carries the marker-derived hint. Rendering keys on render_as, so a chart
// must still render as html with output_type "text" beside it.
describe("message_done after upstream #101 (render_as without a matching output_type)", () => {
  it("keeps the html render hint when output_type says text", () => {
    let s = initialChatState();
    s = ev(s, { type: "message_start", id: "c1", sequence: 3 });
    s = ev(s, { type: "message_delta", id: "c1", delta: "<<<HTML>>>" });
    s = ev(s, { type: "message_done", id: "c1", content: "<html><body>chart</body></html>", output_type: "text", render_as: "html" });
    expect(s.messages.c1).toMatchObject({ renderAs: "html", outputType: "text", isStreaming: false, content: "<html><body>chart</body></html>" });
  });

  it("replays history saved with that shape the same way", () => {
    const s = applyHistory(initialChatState(), [
      { ...wireMsg("h1", 1), sender_type: "persona", content: "<html><body>x</body></html>", render_as: "html", output_type: "text" } as never,
    ]);
    expect(s.messages.h1).toMatchObject({ renderAs: "html", outputType: "text" });
  });

  it("ignores the worker's runner-internal event types if nucleus ever relays them", () => {
    expect(parseEvent({ type: "tool_call_start", id: "c1", tool_call: { name: "web_search", args: { q: "x" } } })).toBeNull();
    expect(parseEvent({ type: "persist_internal_state", id: "c1", metadata: { internal_model_state: [] } })).toBeNull();
  });
});

// Tool activity: the worker emits tool_call_start, nucleus relays it as
// tool_activity, and the bubble shows the server's wording instead of guessing.
describe("tool activity", () => {
  const started = () => ev(initialChatState(), { type: "message_start", id: "m1", sender_name: "Layla" });
  const activity = (label: string, tool = "web_search") =>
    ({ type: "tool_activity", id: "m1", tool, label });

  it("records the server's label on the streaming message", () => {
    const s = ev(started(), activity("Searching the web"));
    expect(s.messages.m1.activity).toBe("Searching the web");
  });

  it("counts as activity, so a long tool call is not read as a stall", () => {
    const s = ev(started(), activity("Running a command", "shell"), NOW + 1000);
    expect(s.messages.m1.isStalled).toBe(false);
    expect(s.messages.m1.lastActivity).toBe(NOW + 1000);
  });

  it("clears once tokens start flowing", () => {
    let s = ev(started(), activity("Searching the web"));
    s = ev(s, { type: "message_delta", id: "m1", delta: "Found " });
    expect(s.messages.m1.activity).toBeNull();
    expect(s.messages.m1.content).toBe("Found ");
  });

  it("is ignored for a message that does not exist", () => {
    const s = ev(initialChatState(), { type: "tool_activity", id: "ghost", tool: "x", label: "Using x" });
    expect(s.messages.ghost).toBeUndefined();
  });

  it("is dropped when the server sent no label", () => {
    expect(parseEvent({ type: "tool_activity", id: "m1", tool: "web_search" })).toBeNull();
  });
});
