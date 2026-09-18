"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ChipInput } from "@/components/ui/chip-input";
import { Label, FieldError } from "@/components/ui/field";
import {
  CAPABILITIES,
  SHELL_COMMANDS,
  THINKING_EFFORTS,
  capabilitySpec,
  formatCapabilityConfig,
  parseCapabilityConfig,
  shellListsProblem,
  type CapabilityArgs,
  type CapabilityConfig,
} from "@/lib/mcp-capabilities";

// Editor for an internal row's capability_config: a checklist of the worker's
// capabilities (ticked = key present), a small form for the ones that take
// arguments, and a JSON view for everything at once. Unknown keys — the
// worker may know capabilities this copy of the catalogue does not — are
// listed and kept verbatim, never dropped.
const slug = (k: string) => k.toLowerCase().replace(/[^a-z0-9]+/g, "-");
const list = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
const inputClass = "h-9 w-full rounded-[8px] border border-line bg-surface px-2.5 text-[13px] outline-none focus:border-accent";
const areaClass = "w-full resize-y rounded-[8px] border border-line bg-surface px-2.5 py-1.5 font-mono text-[12.5px] leading-relaxed outline-none focus:border-accent";

export function CapabilityEditor({ idPrefix, value, onChange, onError }: {
  idPrefix: string;
  value: CapabilityConfig;
  onChange: (next: CapabilityConfig) => void;
  // The JSON view can hold text that does not parse; the host blocks submit
  // while this is non-null.
  onError?: (error: string | null) => void;
}) {
  const [json, setJson] = useState(false);
  const [text, setText] = useState("");
  const [textErr, setTextErr] = useState<string | null>(null);

  const setArgs = (key: string, patch: CapabilityArgs) => onChange({ ...value, [key]: { ...(value[key] ?? {}), ...patch } });
  const toggle = (key: string) => {
    if (key in value) {
      const next = { ...value };
      delete next[key];
      onChange(next);
    } else {
      onChange({ ...value, [key]: structuredClone(capabilitySpec(key)?.defaults ?? {}) });
    }
  };
  const openJson = () => {
    setText(formatCapabilityConfig(value));
    setTextErr(null);
    onError?.(null);
    setJson(true);
  };
  const closeJson = () => {
    if (textErr) return; // keep the user on the broken text, not silently revert
    setJson(false);
  };
  const editText = (t: string) => {
    setText(t);
    const r = parseCapabilityConfig(t);
    setTextErr(r.error ?? null);
    onError?.(r.error ?? null);
    if (r.value) onChange(r.value);
  };

  const unknown = Object.keys(value).filter((k) => !capabilitySpec(k));
  const count = Object.keys(value).length;

  return (
    <fieldset>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <legend className="text-[13px] font-medium text-ink2">Capabilities <span className="text-ink2">({count} on)</span></legend>
        <button type="button" onClick={json ? closeJson : openJson} className="inline-flex cursor-pointer items-center text-[12px] font-semibold text-accent hover:underline">
          {json ? "Back to the list" : "Edit as JSON"}
        </button>
      </div>
      {json ? (
        <div>
          <textarea
            id={`${idPrefix}-cap-json`}
            aria-label="Capabilities JSON"
            rows={10}
            value={text}
            onChange={(e) => editText(e.target.value)}
            spellCheck={false}
            className={areaClass}
          />
          <FieldError>{textErr}</FieldError>
          <p className="mt-1.5 text-[12px] text-ink2">Capability name → its settings, exactly as the AI worker reads it. Keys the list does not know are kept as they are.</p>
        </div>
      ) : (
        <ul className="grid gap-1.5 sm:grid-cols-2">
          {CAPABILITIES.map((c) => {
            const on = c.key in value;
            const id = `${idPrefix}-cap-${slug(c.key)}`;
            return (
              <li key={c.key} className={`rounded-[10px] border px-3 py-2 transition-colors ${on ? "border-accent bg-accent/10" : "border-line bg-surface"} ${on && c.editor ? "sm:col-span-2" : ""}`}>
                <label className="flex cursor-pointer items-start gap-2.5 text-[13px]">
                  <input id={id} type="checkbox" checked={on} onChange={() => toggle(c.key)} className="mt-0.5 accent-[var(--accent)]" />
                  <span className="min-w-0">
                    <span className="font-medium">{c.label}</span>
                    <span className="block text-[12px] text-ink2">{c.blurb}{!c.editor && " No settings yet."}</span>
                  </span>
                </label>
                {on && c.editor && <CapabilityFields kind={c.editor} idPrefix={id} args={value[c.key] ?? {}} onArgs={(patch) => setArgs(c.key, patch)} />}
              </li>
            );
          })}
          {unknown.map((k) => (
            <li key={k} className="rounded-[10px] border border-accent bg-accent/10 px-3 py-2">
              <label className="flex cursor-pointer items-start gap-2.5 text-[13px]">
                <input type="checkbox" checked onChange={() => toggle(k)} className="mt-0.5 accent-[var(--accent)]" />
                <span className="min-w-0">
                  <span className="font-medium">{k}</span>
                  <span className="block text-[12px] text-ink2">Not in this list — its settings are editable as JSON.</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}

const GLOB_FIELDS = [
  ["allowed_patterns", "Allowed globs"],
  ["denied_patterns", "Denied globs"],
  ["protected_patterns", "Read-only globs"],
] as const;

function CapabilityFields({ kind, idPrefix, args, onArgs }: {
  kind: NonNullable<(typeof CAPABILITIES)[number]["editor"]>;
  idPrefix: string;
  args: CapabilityArgs;
  onArgs: (patch: CapabilityArgs) => void;
}) {
  if (kind === "filesystem") {
    return (
      <div className="mt-2 grid gap-2.5 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label htmlFor={`${idPrefix}-root`} className="mb-1 text-[12px]">Root folder</Label>
          <input id={`${idPrefix}-root`} value={String(args.root_dir ?? "")} onChange={(e) => onArgs({ root_dir: e.target.value })} className={`${inputClass} font-mono`} />
          <p className="mt-1 text-[11.5px] text-ink2">Relative to the project folder; the project&apos;s default row points at the folder itself.</p>
        </div>
        {GLOB_FIELDS.map(([f, label]) => (
          <div key={f} className={f === "protected_patterns" ? "sm:col-span-2" : ""}>
            <Label htmlFor={`${idPrefix}-${f}`} className="mb-1 text-[12px]">{label}</Label>
            <ChipInput id={`${idPrefix}-${f}`} label={label} value={list(args[f])} onChange={(v) => onArgs({ [f]: v })} placeholder="Type a glob and press Enter" />
          </div>
        ))}
      </div>
    );
  }
  if (kind === "shell") return <ShellFields idPrefix={idPrefix} args={args} onArgs={onArgs} />;
  if (kind === "web-search") {
    return (
      <div className="mt-2 max-w-xs">
        <Label htmlFor={`${idPrefix}-engine`} className="mb-1 text-[12px]">Search engine</Label>
        <input id={`${idPrefix}-engine`} value={String(args.local ?? "")} onChange={(e) => onArgs({ local: e.target.value })} className={inputClass} />
      </div>
    );
  }
  if (kind === "web-fetch") {
    return (
      <label className="mt-2 flex items-center gap-2 text-[12.5px] text-ink2">
        <input type="checkbox" checked={args.local !== false} onChange={(e) => onArgs({ local: e.target.checked })} className="accent-[var(--accent)]" />
        Fetch pages from this server (local)
      </label>
    );
  }
  return (
    <div className="mt-2 max-w-xs">
      <Label htmlFor={`${idPrefix}-effort`} className="mb-1 text-[12px]">Effort</Label>
      <select id={`${idPrefix}-effort`} value={String(args.effort ?? "medium")} onChange={(e) => onArgs({ effort: e.target.value })} className={inputClass}>
        {THINKING_EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
      </select>
    </div>
  );
}

// The worker's Shell takes one list — an allow list or a block list — and
// refuses to start with both. So the policy is one choice, and every write
// fills the chosen list and empties the other.
type ShellPolicy = "any" | "only" | "all-but";
const POLICIES: readonly { id: ShellPolicy; label: string; blurb: string }[] = [
  { id: "any", label: "Any command", blurb: "Nothing is filtered by name." },
  { id: "only", label: "Only these", blurb: "Everything else is refused." },
  { id: "all-but", label: "All but these", blurb: "Anything not listed may run." },
];

function ShellFields({ idPrefix, args, onArgs }: { idPrefix: string; args: CapabilityArgs; onArgs: (patch: CapabilityArgs) => void }) {
  const allowed = list(args.allowed_commands);
  const denied = list(args.denied_commands);
  // The lists say which policy is in force. When both are empty they cannot,
  // and the radio keeps the last policy the lists (or the user) named — an
  // allow list being emptied stays "Only these" instead of jumping to "Any
  // command" under the user.
  const implied: ShellPolicy | null = allowed.length ? "only" : denied.length ? "all-but" : null;
  const [chosen, setChosen] = useState<ShellPolicy>(implied ?? "any");
  const [seen, setSeen] = useState(implied);
  if (implied !== seen) {
    setSeen(implied);
    if (implied) setChosen(implied);
  }
  const policy = implied ?? chosen;
  const collision = shellListsProblem({ shell: args });
  const picks = policy === "only" ? allowed : denied;
  // A saved command the catalogue lacks stays visible, so it can be unpicked.
  const commands = [...SHELL_COMMANDS, ...picks.filter((c) => !(SHELL_COMMANDS as readonly string[]).includes(c))];
  const write = (next: string[]) => onArgs({ allowed_commands: policy === "only" ? next : [], denied_commands: policy === "all-but" ? next : [] });
  const pick = (cmd: string) => write(picks.includes(cmd) ? picks.filter((c) => c !== cmd) : [...picks, cmd]);
  const choose = (p: ShellPolicy) => {
    setChosen(p);
    onArgs({ allowed_commands: [], denied_commands: [] });
  };

  return (
    <div className="mt-2 grid gap-2.5 sm:grid-cols-2">
      <div>
        <Label htmlFor={`${idPrefix}-cwd`} className="mb-1 text-[12px]">Working folder</Label>
        <input id={`${idPrefix}-cwd`} value={String(args.cwd ?? "")} onChange={(e) => onArgs({ cwd: e.target.value })} className={`${inputClass} font-mono`} />
      </div>
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Label htmlFor={`${idPrefix}-timeout`} className="mb-1 text-[12px]">Timeout (s)</Label>
          <input id={`${idPrefix}-timeout`} type="number" min={1} step={1} value={String(args.default_timeout ?? "")} onChange={(e) => onArgs({ default_timeout: Number(e.target.value) })} className={inputClass} />
        </div>
        <div className="flex-1">
          <Label htmlFor={`${idPrefix}-max`} className="mb-1 text-[12px]">Max output (chars)</Label>
          <input id={`${idPrefix}-max`} type="number" min={1} step={1} value={String(args.max_output_chars ?? "")} onChange={(e) => onArgs({ max_output_chars: Number(e.target.value) })} className={inputClass} />
        </div>
      </div>
      <div className="sm:col-span-2">
        <p className="mb-1 text-[12px] font-medium text-ink2">Commands</p>
        {collision ? (
          <div>
            <FieldError>{collision}</FieldError>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={() => onArgs({ denied_commands: [] })}>Keep the allow list ({allowed.length})</Button>
              <Button type="button" size="sm" onClick={() => onArgs({ allowed_commands: [] })}>Keep the block list ({denied.length})</Button>
            </div>
          </div>
        ) : (
          <>
            <div role="radiogroup" aria-label="Command policy" className="grid gap-1">
              {POLICIES.map((p) => (
                <label key={p.id} className="flex cursor-pointer items-center gap-1.5 text-[12.5px]">
                  <input type="radio" name={`${idPrefix}-policy`} checked={policy === p.id} onChange={() => choose(p.id)} className="accent-[var(--accent)]" />
                  {p.label} <span className="text-ink2">— {p.blurb}</span>
                </label>
              ))}
            </div>
            {policy !== "any" && (
              <div role="group" aria-label={policy === "only" ? "Allowed commands" : "Blocked commands"} className="mt-2 flex flex-wrap gap-1.5">
                {commands.map((cmd) => {
                  const on = picks.includes(cmd);
                  return (
                    <button key={cmd} type="button" aria-pressed={on} onClick={() => pick(cmd)}
                      className={`cursor-pointer rounded-full border px-2 py-0.5 font-mono text-[11.5px] transition-colors ${on ? "border-accent bg-accent/15 text-accent" : "border-line text-ink2 hover:border-accent/50"}`}>
                      {cmd}
                    </button>
                  );
                })}
              </div>
            )}
            {policy === "only" && picks.length === 0 && (
              <p className="mt-1.5 text-[11.5px] text-warn">Nothing picked yet, so any command may run.</p>
            )}
          </>
        )}
      </div>
      <label className="flex items-center gap-2 text-[12.5px] text-ink2 sm:col-span-2">
        <input type="checkbox" checked={args.allow_interactive !== false} onChange={(e) => onArgs({ allow_interactive: e.target.checked })} className="accent-[var(--accent)]" />
        Allow interactive commands
      </label>
    </div>
  );
}
