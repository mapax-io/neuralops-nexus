import { describe, expect, it } from "vitest";
import { resolveSubmit } from "./slash";

// DECISIONS §13: /invite detects persona vs human from the argument; email
// invites default to THIS TOPIC, "project" widens; personas join the project.
describe("resolveSubmit /invite", () => {
  it("treats a bare or @-prefixed name as a persona (project scope always)", () => {
    expect(resolveSubmit("/invite @Ryan")).toEqual({ kind: "invite", personaName: "Ryan", scope: "project" });
    expect(resolveSubmit("/invite Ryan")).toEqual({ kind: "invite", personaName: "Ryan", scope: "project" });
  });

  it("email invites default to the current topic", () => {
    expect(resolveSubmit("/invite sara@example.com")).toEqual({ kind: "invite", email: "sara@example.com", scope: "topic" });
  });

  it("a trailing 'project' widens the email invite", () => {
    expect(resolveSubmit("/invite sara@example.com project")).toEqual({ kind: "invite", email: "sara@example.com", scope: "project" });
  });

  it("rejects missing target, junk scopes, and trailing words", () => {
    expect(resolveSubmit("/invite").kind).toBe("invalid");
    expect(resolveSubmit("/invite sara@example.com everywhere").kind).toBe("invalid");
    expect(resolveSubmit("/invite a b c").kind).toBe("invalid");
  });
});

describe("resolveSubmit management commands", () => {
  it("maps /add-* and /list-* to their intelligence sections", () => {
    expect(resolveSubmit("/add-model")).toEqual({ kind: "intel", section: "models", create: true });
    expect(resolveSubmit("/list-mcps")).toEqual({ kind: "intel", section: "mcp", create: false });
    expect(resolveSubmit("/add-persona")).toEqual({ kind: "intel", section: "personas", create: true });
    expect(resolveSubmit("/edit-persona")).toEqual({ kind: "intel", section: "personas", create: false });
  });

  it("routes schedule commands to the schedules pane", () => {
    expect(resolveSubmit("/schedule")).toEqual({ kind: "schedules" });
    expect(resolveSubmit("/list-schedules")).toEqual({ kind: "schedules" });
  });

  it("leaves ordinary messages and other commands alone", () => {
    expect(resolveSubmit("hello /invite later").kind).toBe("send");
    expect(resolveSubmit("/add-model with args").kind).toBe("send");
    expect(resolveSubmit("/changeusername Tauqeer")).toEqual({ kind: "changeusername", newName: "Tauqeer" });
    expect(resolveSubmit("/nonsense").kind).toBe("invalid");
  });
});

describe("resolveSubmit retired commands", () => {
  // Agents collapsed into personas server-side — the commands would open a
  // section that no longer exists, so they must read as unknown.
  it("no longer knows /add-agent or /list-agents", () => {
    expect(resolveSubmit("/add-agent").kind).toBe("invalid");
    expect(resolveSubmit("/list-agents").kind).toBe("invalid");
  });
});
