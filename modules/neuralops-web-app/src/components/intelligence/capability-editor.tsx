"use client";

import { useState } from "react";
import { Label, FieldError } from "@/components/ui/field";
import {
  CAPABILITIES,
  SHELL_COMMANDS,
  THINKING_EFFORTS,
  capabilitySpec,
  formatCapabilityConfig,
  parseCapabilityConfig,
  type CapabilityArgs,
  type CapabilityConfig,
} from "@/lib/mcp-capabilities";

// Editor for an internal row's capability_config: a checklist of the worker's
// capabilities (ticked = key present), a small form for the ones that take
// arguments, and a JSON view for everything at once. Unknown keys — the
// worker may know capabilities this copy of the catalogue does not — are
// listed and kept verbatim, never dropped.
const slug = (k: string) => k.toLowerCase().replace(/[^a-z0-9]+/g, "-");
const lines = (v: unknown): string => (Array.isArray(v) ? v.map(String).join("\n") : "");
const splitLines = (t: string): string[] => t.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
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
                  <span className="block text-[12px] text-ink2">Set by the server — edit its settings as JSON.</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}

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
        {(["allowed_patterns", "denied_patterns", "protected_patterns"] as const).map((f) => (
          <div key={f} className={f === "protected_patterns" ? "sm:col-span-2" : ""}>
            <Label htmlFor={`${idPrefix}-${f}`} className="mb-1 text-[12px]">
              {f === "allowed_patterns" ? "Allowed globs" : f === "denied_patterns" ? "Denied globs" : "Read-only globs"} <span className="text-ink2">(one per line)</span>
            </Label>
            <textarea id={`${idPrefix}-${f}`} rows={2} value={lines(args[f])} onChange={(e) => onArgs({ [f]: splitLines(e.target.value) })} spellCheck={false} className={areaClass} />
          </div>
        ))}
      </div>
    );
  }
  if (kind === "shell") {
    const allowed = list(args.allowed_commands);
    const denied = list(args.denied_commands);
    const flip = (field: "allowed_commands" | "denied_commands", cmd: string) => {
      const cur = list(args[field]);
      onArgs({ [field]: cur.includes(cmd) ? cur.filter((c) => c !== cmd) : [...cur, cmd] });
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
        {(["allowed_commands", "denied_commands"] as const).map((field) => (
          <div key={field} className="sm:col-span-2">
            <p className="mb-1 text-[12px] font-medium text-ink2">{field === "allowed_commands" ? "Allowed commands" : "Denied commands"}</p>
            <div role="group" aria-label={field === "allowed_commands" ? "Allowed commands" : "Denied commands"} className="flex flex-wrap gap-1.5">
              {SHELL_COMMANDS.map((cmd) => {
                const on = (field === "allowed_commands" ? allowed : denied).includes(cmd);
                return (
                  <button key={cmd} type="button" aria-pressed={on} onClick={() => flip(field, cmd)}
                    className={`rounded-full border px-2 py-0.5 font-mono text-[11.5px] transition-colors ${on ? "border-accent bg-accent/15 text-accent" : "border-line text-ink2 hover:border-accent/50"}`}>
                    {cmd}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <label className="flex items-center gap-2 text-[12.5px] text-ink2 sm:col-span-2">
          <input type="checkbox" checked={args.allow_interactive !== false} onChange={(e) => onArgs({ allow_interactive: e.target.checked })} className="accent-[var(--accent)]" />
          Allow interactive commands
        </label>
      </div>
    );
  }
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
