// Server-shipped role templates carry a {PERSONA_NAME} token (the only
// placeholder they use) and nothing fills it at runtime — the role is stored
// and sent to the model verbatim. So the persona dialogs fill it: live in the
// Role field as the name is typed, and once more on save so no token is ever
// stored.

import { markdownToPlain } from "@/lib/markdown";

export const PERSONA_NAME_TOKEN = "{PERSONA_NAME}";

export function hasPersonaNameToken(text: string): boolean {
  return text.includes(PERSONA_NAME_TOKEN);
}

// A blank name keeps the token visible — replacing it with nothing would
// silently produce "You are , the git expert."
export function fillPersonaName(text: string, name: string): string {
  const n = name.trim();
  return n ? text.split(PERSONA_NAME_TOKEN).join(n) : text;
}

// What a card shows for a persona that has no description: the role, read
// as prose. Shipped templates open with a YAML front matter block and a
// shouting heading, and neither says what the persona does — the first
// body sentence does. Front matter and headings go; markdown becomes plain.
export function rolePreview(role: string): string {
  const body = role
    .replace(/^\uFEFF?\s*---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, "")
    .replace(/^\s{0,3}#{1,6}\s+.*$/gm, " ");
  return markdownToPlain(body);
}
