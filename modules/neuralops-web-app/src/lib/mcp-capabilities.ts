// Built-in ("internal") tool capabilities a persona can mount without any MCP
// server: pydantic-ai provides them in-process. An internal MCPServer row is
// name + project + `capability_config`, a map of capability name → arguments,
// stored opaque by nucleus and interpreted by the AI worker.
//
// This catalogue is a COPY across the service boundary (like nucleus's own
// settings.MCP_CAPABILITY_TEMPLATE): keys are the worker's capability names
// (nexus-ai apps/schemas/trigger.py NativePydanticAICapabilities), defaults
// are that template's. Re-derive it when either changes.

export type CapabilityArgs = Record<string, unknown>;
export type CapabilityConfig = Record<string, CapabilityArgs>;

export type CapabilityEditorKind = "filesystem" | "shell" | "web-search" | "web-fetch" | "thinking";

export interface CapabilitySpec {
  key: string;      // the worker's name, verbatim — it is the JSON key
  label: string;
  blurb: string;
  defaults: CapabilityArgs;
  editor?: CapabilityEditorKind; // absent = the worker takes no arguments yet
}

// Valid Shell commands — trigger.py's ShellCommands enum, verbatim.
export const SHELL_COMMANDS = ["ls", "touch", "rm", "git", "cd", "cat", "echo", "grep", "pwd", "mkdir", "cp", "mv", "head", "tail", "curl"] as const;
export const THINKING_EFFORTS = ["minimal", "low", "medium", "high", "xhigh"] as const;

// Read-only globs the worker protects by default.
export const DEFAULT_PROTECTED_PATTERNS = [".git/*", ".env", ".env.*", "*.pem", "*.key", "**/secrets*"];

export const CAPABILITIES: readonly CapabilitySpec[] = [
  { key: "Filesystem", label: "Filesystem", blurb: "Read and write files under the project folder.", editor: "filesystem",
    defaults: { root_dir: ".", allowed_patterns: [], denied_patterns: [], protected_patterns: [...DEFAULT_PROTECTED_PATTERNS] } },
  { key: "Shell", label: "Shell", blurb: "Run an allow-listed set of commands in the project folder.", editor: "shell",
    defaults: { cwd: ".", allowed_commands: ["ls", "touch", "cat", "cd", "grep", "cp", "mkdir"], denied_commands: [], allow_interactive: true, default_timeout: 30, max_output_chars: 50000 } },
  { key: "Web Search", label: "Web search", blurb: "Search the web.", editor: "web-search", defaults: { local: "duckduckgo" } },
  { key: "Web Fetch", label: "Web fetch", blurb: "Fetch and read web pages.", editor: "web-fetch", defaults: { local: true } },
  { key: "Thinking", label: "Thinking", blurb: "Extended reasoning before answering.", editor: "thinking", defaults: { effort: "medium" } },
  { key: "Planning", label: "Planning", blurb: "Plan multi-step work before acting.", defaults: {} },
  { key: "Memory", label: "Memory", blurb: "Remember across conversations.", defaults: {} },
  { key: "Sub Agents", label: "Sub-agents", blurb: "Delegate sub-tasks to helper agents.", defaults: {} },
  { key: "Dynamic Workflow", label: "Dynamic workflow", blurb: "Build and run multi-step workflows.", defaults: {} },
  { key: "Advisor", label: "Advisor", blurb: "Ask a second model when stuck.", defaults: {} },
  { key: "Tool Search", label: "Tool search", blurb: "Find the right tool among many.", defaults: {} },
  { key: "Compaction", label: "Compaction", blurb: "Summarise long conversations to stay within context.", defaults: {} },
  { key: "Skills", label: "Skills", blurb: "Load reusable skill documents.", defaults: {} },
  { key: "Repo Context", label: "Repo context", blurb: "Understand a code repository.", defaults: {} },
  { key: "X Search", label: "X search", blurb: "Search posts on X.", defaults: {} },
  { key: "Stack One", label: "Stack One", blurb: "StackOne integrations.", defaults: {} },
  { key: "Local Stack", label: "Local stack", blurb: "Local service stack access.", defaults: {} },
  { key: "Gaurdrails", label: "Guardrails", blurb: "Constrain what the persona may do.", defaults: {} },
  { key: "Spend Limits", label: "Spend limits", blurb: "Cap token and tool spend.", defaults: {} },
  { key: "Tool Approval", label: "Tool approval", blurb: "Ask before running sensitive tools.", defaults: {} },
  { key: "Capability Creation", label: "Capability creation", blurb: "Let the persona define new capabilities.", defaults: {} },
];

// The capabilities every new project's default row carries (nucleus
// DEFAULT_PROJECT_CAPABILITIES) — also the sensible starting ticks for a new row.
export const DEFAULT_CAPABILITY_KEYS = ["Filesystem", "Shell", "Web Search", "Web Fetch"] as const;

export const capabilitySpec = (key: string): CapabilitySpec | undefined => CAPABILITIES.find((c) => c.key === key);

// Display label for a key — unknown keys (worker-side additions this copy
// does not know yet) show verbatim rather than vanishing.
export const capabilityLabel = (key: string): string => capabilitySpec(key)?.label ?? key;

// Labels for a row's chips, in catalogue order, unknown keys last.
export function capabilityLabels(config: CapabilityConfig | null | undefined): string[] {
  const keys = Object.keys(config ?? {});
  const known = CAPABILITIES.filter((c) => keys.includes(c.key)).map((c) => c.label);
  const unknown = keys.filter((k) => !capabilitySpec(k));
  return [...known, ...unknown];
}

export function defaultCapabilityConfig(keys: readonly string[] = DEFAULT_CAPABILITY_KEYS): CapabilityConfig {
  const out: CapabilityConfig = {};
  for (const k of keys) out[k] = structuredClone(capabilitySpec(k)?.defaults ?? {});
  return out;
}

// The wire shape: a JSON object whose values are objects (one per capability).
export function parseCapabilityConfig(text: string): { value?: CapabilityConfig; error?: string } {
  const bad = "Capabilities must be a JSON object of capability name → settings, like {\"Web Search\": {\"local\": \"duckduckgo\"}}.";
  const t = text.trim();
  if (!t) return { value: {} };
  try {
    const v: unknown = JSON.parse(t);
    if (!v || typeof v !== "object" || Array.isArray(v)) return { error: bad };
    for (const [k, args] of Object.entries(v as Record<string, unknown>)) {
      if (!args || typeof args !== "object" || Array.isArray(args)) return { error: `"${k}" must map to a settings object (use {} for none).` };
    }
    return { value: v as CapabilityConfig };
  } catch {
    return { error: bad };
  }
}

export const formatCapabilityConfig = (c: CapabilityConfig | null | undefined) => (c && Object.keys(c).length ? JSON.stringify(c, null, 2) : "");
