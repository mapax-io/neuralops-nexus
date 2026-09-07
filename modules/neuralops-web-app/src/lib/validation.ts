// Shared form validation. Every validator returns an error string, or null
// when the value is acceptable — so callers do `setErr(validateX(v))`.

// Display names for entities (projects, channels, models, agents, MCP
// servers): letters, numbers, spaces, and a few safe separators. No angle
// brackets, slashes, quotes, or other control/markup characters.
const NAME_ALLOWED = /^[\p{L}\p{N} ._&'()-]+$/u;
// Mentionable handles (personas): what the chat @-parser accepts — word
// characters only, no spaces (they become `@name` tokens).
const MENTION_ALLOWED = /^[A-Za-z0-9_]+$/;

export interface NameOpts {
  label?: string;          // e.g. "project" — used in messages
  min?: number;
  max?: number;
  existing?: string[];     // case-insensitive uniqueness check
  current?: string;        // value being edited — excluded from the uniqueness check
}

export function validateName(value: string, opts: NameOpts = {}): string | null {
  const { label = "name", min = 1, max = 80, existing, current } = opts;
  const t = value.trim();
  if (!t) return `Enter a ${label}.`;
  if (t.length < min) return `The ${label} must be at least ${min} characters.`;
  if (t.length > max) return `Keep the ${label} under ${max} characters.`;
  if (!NAME_ALLOWED.test(t)) return "Use letters, numbers, spaces, and . _ & ' ( ) - only — no special characters.";
  if (existing && current?.trim().toLowerCase() !== t.toLowerCase()
      && existing.some((e) => e.trim().toLowerCase() === t.toLowerCase())) {
    return `A ${label} named "${t}" already exists.`;
  }
  return null;
}

// Persona / mention names.
export function validateMentionName(value: string, opts: { existing?: string[]; current?: string; reserved?: Set<string> } = {}): string | null {
  const t = value.trim();
  if (!t) return "Enter a name.";
  if (t.length > 50) return "Keep the name under 50 characters.";
  if (!MENTION_ALLOWED.test(t)) return "Letters, numbers, and underscores only — this becomes an @mention.";
  if (opts.reserved?.has(t.toLowerCase())) return `"${t}" is a reserved word — pick another name.`;
  if (opts.existing && opts.current?.trim().toLowerCase() !== t.toLowerCase()
      && opts.existing.some((e) => e.trim().toLowerCase() === t.toLowerCase())) {
    return `A persona named "${t}" already exists here.`;
  }
  return null;
}

export function validateRequired(value: string, label: string): string | null {
  return value.trim() ? null : `Enter ${label}.`;
}

// URLs (MCP endpoints, context web sources, model api_base, links). http(s)
// by default; a caller that speaks another protocol names its schemes
// (a WebSocket MCP server takes ws:// or wss://).
export function validateUrl(value: string, opts: { label?: string; required?: boolean; schemes?: readonly string[] } = {}): string | null {
  const { label = "a URL", required = true, schemes = ["http:", "https:"] } = opts;
  const t = value.trim();
  if (!t) return required ? `Enter ${label}.` : null;
  const list = schemes.map((s) => `${s}//`).join(" or ");
  let u: URL;
  try { u = new URL(t); } catch { return `Enter a valid URL (including ${list}).`; }
  if (!schemes.includes(u.protocol)) return `The URL must start with ${list}.`;
  return null;
}

export function validateNumber(value: number | string, opts: { label?: string; min?: number; max?: number; integer?: boolean } = {}): string | null {
  const { label = "a number", min, max, integer } = opts;
  const n = typeof value === "number" ? value : Number(value.trim());
  if (value === "" || Number.isNaN(n)) return `Enter ${label}.`;
  if (integer && !Number.isInteger(n)) return `${label[0].toUpperCase()}${label.slice(1)} must be a whole number.`;
  if (min != null && n < min) return `Must be at least ${min}.`;
  if (max != null && n > max) return `Must be at most ${max}.`;
  return null;
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function validateEmail(value: string): string | null {
  return EMAIL_RE.test(value.trim()) ? null : "Enter a valid email address.";
}
