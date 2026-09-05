// Character ranges of @mention and /command tokens, for the composer's pill
// highlighting. PURELY VISUAL: the underlying text (the markdown wire format the
// backend parses) is never changed — a ProseMirror decoration just paints these
// ranges as pills. So there is no serialization, draft-restore, or swarm-gate
// impact; drafts round-trip as plain text and re-highlight on their own.
//
// A token is pilled ONLY when it matches a real value — a known @persona or
// @directive, or a known /command — so a typo (@asdf, /qwer) stays plain text.

// Pill flavors: @persona/@directive (accent), @you (unique), @teammate (blue),
// /command (green — composer only).
export type PillKind = "mention" | "self" | "human" | "command";

export interface KnownSets {
  mentions: Set<string>; // personas + @directive names (lowercase)
  self: Set<string>; //     the signed-in user's own name — unique color
  humans: Set<string>; //   other teammates
  commands: Set<string>; // slash command names
}

// The color for an @name — shared by the composer decoration AND the chat
// message renderer so "@you" reads the same everywhere. @persona/@directive win
// over @you which wins over @teammate (rare name collisions).
export function mentionKind(
  name: string,
  known: Pick<KnownSets, "mentions" | "self" | "humans">,
): PillKind | null {
  const w = name.toLowerCase();
  return known.mentions.has(w) ? "mention" : known.self.has(w) ? "self" : known.humans.has(w) ? "human" : null;
}

export interface PillRange {
  start: number;
  end: number;
  kind: PillKind; // drives the pill color
}

// @word at a token boundary — the negative lookbehind skips emails (user@host)
// and @@; word is captured (\w+, matching the backend's mention parsing).
const MENTION_RE = /(?<![\w@/])@(\w+)/g;
// /word only after whitespace or start — skips URLs (https://…, a/b) while
// still catching a leading /invite and a trailing /swarm. Hyphens allowed
// (add-mcp), captured without the leading slash.
const COMMAND_RE = /(?<!\S)\/(\w[\w-]*)/g;

export function findPillRanges(text: string, known: KnownSets): PillRange[] {
  const ranges: PillRange[] = [];
  MENTION_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = MENTION_RE.exec(text)) !== null) {
    const kind = mentionKind(m[1], known);
    if (kind) ranges.push({ start: m.index, end: m.index + m[0].length, kind });
  }
  COMMAND_RE.lastIndex = 0;
  while ((m = COMMAND_RE.exec(text)) !== null) {
    if (known.commands.has(m[1].toLowerCase())) {
      ranges.push({ start: m.index, end: m.index + m[0].length, kind: "command" });
    }
  }
  return ranges.sort((a, b) => a.start - b.start);
}
