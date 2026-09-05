// Slash commands. Server reality: /swarm is the ONLY backend command (a
// bare substring directive, needs ≥2 mentioned personas or it silently
// degrades); /changeusername is frontend-handled via its endpoint. Anything
// else single-token is blocked with a hint; "/word rest" sends as text.

export interface SlashCommand {
  name: string;
  hint: string;
  usage: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "swarm", hint: "Send this task to multiple personas that collaborate", usage: "@A @B your task /swarm" },
  { name: "invite", hint: "Add a persona or invite a person here", usage: "/invite @Persona · /invite email@example.com [project]" },
  { name: "schedule", hint: "Schedule a persona to run in this topic", usage: "/schedule" },
  { name: "list-schedules", hint: "See this topic's schedules", usage: "/list-schedules" },
  { name: "add-persona", hint: "Create a persona (model, optional advisor and tools)", usage: "/add-persona" },
  { name: "list-personas", hint: "See all personas", usage: "/list-personas" },
  { name: "edit-persona", hint: "Edit a persona", usage: "/edit-persona" },
  { name: "add-model", hint: "Register an AI model", usage: "/add-model" },
  { name: "list-models", hint: "See registered AI models", usage: "/list-models" },
  { name: "add-mcp", hint: "Register an MCP tool server", usage: "/add-mcp" },
  { name: "list-mcps", hint: "See MCP servers", usage: "/list-mcps" },
  { name: "changeusername", hint: "Change your display name on this server", usage: "/changeusername NewName" },
];

// Single-token commands that jump to an intelligence section — optionally
// opening its create dialog (the one-shot intelCreate intent in ui.store).
export const INTEL_COMMANDS: Record<string, { section: "models" | "mcp" | "personas"; create: boolean }> = {
  "add-model": { section: "models", create: true },
  "list-models": { section: "models", create: false },
  "add-mcp": { section: "mcp", create: true },
  "list-mcps": { section: "mcp", create: false },
  "add-persona": { section: "personas", create: true },
  "list-personas": { section: "personas", create: false },
  "edit-persona": { section: "personas", create: false },
};

// Popover trigger: the whole input is a single "/token" being typed.
export function slashTriggerQuery(text: string): string | null {
  const m = /^\/([\w-]*)$/.exec(text);
  return m ? m[1].toLowerCase() : null;
}

export function mentionCount(text: string, reserved: Set<string>): number {
  const names = new Set<string>();
  for (const m of text.matchAll(/@([\w]+)/g)) {
    if (!reserved.has(m[1].toLowerCase())) names.add(m[1].toLowerCase());
  }
  return names.size;
}

export type SlashAction =
  | { kind: "send" } // not a command — send as a normal message
  | { kind: "changeusername"; newName: string }
  // DECISIONS §13: persona vs human detected from the argument — an email
  // has an @ in the MIDDLE; a persona is a bare name or a leading-@ handle.
  | { kind: "invite"; email?: string; personaName?: string; scope: "project" | "topic" }
  | { kind: "intel"; section: "models" | "mcp" | "personas"; create: boolean }
  | { kind: "schedules" }
  | { kind: "invalid"; message: string };

const EMAIL_RE = /^\S+@\S+\.\S+$/;
const INVITE_USAGE = "Usage: /invite @Persona — or — /invite email@example.com [project]";

export function resolveSubmit(text: string): SlashAction {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return { kind: "send" };

  const [head, ...rest] = trimmed.split(/\s+/);
  const cmd = head.slice(1).toLowerCase();

  if (cmd === "swarm") {
    if (rest.length === 0) return { kind: "invalid", message: "Swarm needs a task and at least two personas: @A @B your task /swarm" };
    return { kind: "send" }; // backend directive — rides in the message
  }
  if (cmd === "invite") {
    const [target, scopeArg, ...extra] = rest;
    if (!target || extra.length > 0) return { kind: "invalid", message: INVITE_USAGE };
    // DECISIONS §13: email invites default to THIS TOPIC; a trailing
    // "project" widens to the whole project. Personas always join the project.
    const scope = scopeArg === "project" ? "project" : scopeArg === undefined || scopeArg === "topic" ? "topic" : null;
    if (scope === null) return { kind: "invalid", message: INVITE_USAGE };
    if (EMAIL_RE.test(target)) return { kind: "invite", email: target, scope };
    const personaName = target.replace(/^@/, "");
    if (!/^[\w-]+$/.test(personaName)) return { kind: "invalid", message: INVITE_USAGE };
    return { kind: "invite", personaName, scope: "project" };
  }
  if (rest.length === 0 && INTEL_COMMANDS[cmd]) {
    return { kind: "intel", ...INTEL_COMMANDS[cmd] };
  }
  if (rest.length === 0 && (cmd === "schedule" || cmd === "list-schedules")) {
    return { kind: "schedules" };
  }
  if (cmd === "changeusername") {
    const newName = rest.join(" ").trim();
    if (!/^[a-zA-Z0-9_]{2,30}$/.test(newName)) {
      return { kind: "invalid", message: "Usage: /changeusername NewName — 2–30 characters, letters, digits, and _ only." };
    }
    return { kind: "changeusername", newName };
  }
  if (rest.length === 0) {
    return { kind: "invalid", message: `Unknown command: /${cmd}` };
  }
  return { kind: "send" }; // "/word more text" is an ordinary message
}
