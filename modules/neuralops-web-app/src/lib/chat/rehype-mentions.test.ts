import { describe, expect, it } from "vitest";
import type { KnownSets } from "@/lib/composer/mention-ranges";
import { rehypeMentions } from "./rehype-mentions";

const KNOWN: KnownSets = {
  mentions: new Set(["pv12", "chart"]),
  self: new Set(["project1_pv"]),
  humans: new Set(["tahayabali2"]),
  commands: new Set(["swarm", "invite"]),
};

interface Node {
  type?: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: Node[];
}

// A paragraph of plain text, the shape remark-rehype produces for a message.
const para = (text: string): Node => ({
  type: "root",
  children: [{ type: "element", tagName: "p", children: [{ type: "text", value: text }] }],
});

function run(tree: Node, known: KnownSets = KNOWN): Node {
  rehypeMentions(known)()(tree);
  return tree;
}

/** Flatten a transformed tree to "text" and "<class>:text" tokens. */
function tokens(node: Node): string[] {
  if (node.type === "text") return [node.value ?? ""];
  const cls = (node.properties?.className as string[] | undefined)?.[0];
  const inner = (node.children ?? []).flatMap(tokens);
  return cls ? [`${cls}:${inner.join("")}`] : inner;
}

const render = (text: string, known?: KnownSets) => tokens(run(para(text), known));

describe("rehypeMentions", () => {
  it("pills a known persona", () => {
    expect(render("@pv12 hi")).toEqual(["nx-mention-pill:@pv12", " hi"]);
  });

  it("leaves an unknown name as plain text", () => {
    expect(render("@nobody hi")).toEqual(["@nobody hi"]);
  });

  it("gives you, a teammate and a persona their own flavours", () => {
    expect(render("@project1_pv @tahayabali2 @pv12")).toEqual([
      "nx-self-pill:@project1_pv",
      " ",
      "nx-human-pill:@tahayabali2",
      " ",
      "nx-mention-pill:@pv12",
    ]);
  });

  it("keeps the surrounding text intact", () => {
    expect(render("hey @pv12 can you look?")).toEqual(["hey ", "nx-mention-pill:@pv12", " can you look?"]);
  });

  it("pills every occurrence in one line", () => {
    expect(render("@pv12 and @pv12")).toEqual([
      "nx-mention-pill:@pv12", " and ", "nx-mention-pill:@pv12",
    ]);
  });

  // Rules inherited from findPillRanges — the composer's, so both agree.
  it("does not touch an email address", () => {
    expect(render("mail user@pv12 please")).toEqual(["mail user@pv12 please"]);
  });

  it("does not pill slash commands — those are composer affordances", () => {
    expect(render("/swarm @pv12")).toEqual(["/swarm ", "nx-mention-pill:@pv12"]);
  });

  it("does nothing when nothing is known yet", () => {
    const empty: KnownSets = { mentions: new Set(), self: new Set(), humans: new Set(), commands: new Set() };
    expect(render("@pv12 hi", empty)).toEqual(["@pv12 hi"]);
  });
});

describe("rehypeMentions — text that must stay verbatim", () => {
  const wrapped = (tagName: string): Node => ({
    type: "root",
    children: [{ type: "element", tagName, children: [{ type: "text", value: "@pv12" }] }],
  });

  it.each(["code", "pre", "a"])("does not touch a mention inside <%s>", (tag) => {
    expect(tokens(run(wrapped(tag)))).toEqual(["@pv12"]);
  });

  it("does not touch a mention in a fenced block (pre > code)", () => {
    const tree: Node = {
      type: "root",
      children: [{
        type: "element", tagName: "pre",
        children: [{ type: "element", tagName: "code", children: [{ type: "text", value: "@pv12" }] }],
      }],
    };
    expect(tokens(run(tree))).toEqual(["@pv12"]);
  });
});

describe("rehypeMentions — nesting", () => {
  it("reaches a mention inside a list item and emphasis", () => {
    const tree: Node = {
      type: "root",
      children: [{
        type: "element", tagName: "ul",
        children: [{
          type: "element", tagName: "li",
          children: [
            { type: "text", value: "ask " },
            { type: "element", tagName: "em", children: [{ type: "text", value: "@pv12" }] },
          ],
        }],
      }],
    };
    expect(tokens(run(tree))).toEqual(["ask ", "nx-mention-pill:@pv12"]);
  });
});
