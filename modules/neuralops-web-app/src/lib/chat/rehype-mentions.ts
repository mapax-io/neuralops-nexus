import { findPillRanges, type KnownSets, type PillKind } from "@/lib/composer/mention-ranges";

// Minimal hast shape — the same local typing message-item.tsx already uses,
// rather than pulling in @types/hast for four fields.
interface HastNode {
  type?: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const PILL_CLASS: Record<PillKind, string> = {
  mention: "nx-mention-pill",
  self: "nx-self-pill",
  human: "nx-human-pill",
  command: "nx-command-pill",
};

// Text inside these renders verbatim: a mention in a code sample or an
// already-linked URL must stay exactly as written.
const OPAQUE = new Set(["code", "pre", "a"]);

/**
 * Paints @mentions in a rendered message as pills, matching the composer.
 *
 * Uses the same findPillRanges() the composer's ProseMirror decoration uses,
 * so "valid" means the same thing in both places: a known persona, directive
 * or teammate is a pill, and anything else (a typo, an unknown name) stays
 * plain text. Purely visual — the message's markdown is untouched.
 *
 * /commands are deliberately NOT pilled here: they are composer affordances
 * that the server consumes, not content of a sent message.
 */
export function rehypeMentions(known: KnownSets) {
  const active = known.mentions.size > 0 || known.self.size > 0 || known.humans.size > 0;

  return () => (tree: HastNode) => {
    if (!active) return;

    const walk = (node: HastNode) => {
      if (!node.children?.length) return;
      if (node.tagName && OPAQUE.has(node.tagName)) return;

      const next: HastNode[] = [];
      for (const child of node.children) {
        if (child.type !== "text" || !child.value) {
          walk(child);
          next.push(child);
          continue;
        }
        const text = child.value;
        const ranges = findPillRanges(text, known).filter((r) => r.kind !== "command");
        if (!ranges.length) {
          next.push(child);
          continue;
        }
        let at = 0;
        for (const range of ranges) {
          if (range.start > at) next.push({ type: "text", value: text.slice(at, range.start) });
          next.push({
            type: "element",
            tagName: "span",
            properties: { className: [PILL_CLASS[range.kind]] },
            children: [{ type: "text", value: text.slice(range.start, range.end) }],
          });
          at = range.end;
        }
        if (at < text.length) next.push({ type: "text", value: text.slice(at) });
      }
      node.children = next;
    };

    walk(tree);
  };
}
