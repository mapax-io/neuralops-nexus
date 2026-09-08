import { describe, expect, it } from "vitest";
import { fillPersonaName, hasPersonaNameToken, PERSONA_NAME_TOKEN, rolePreview } from "./persona-template";

describe("fillPersonaName", () => {
  it("replaces every {PERSONA_NAME} with the trimmed name", () => {
    expect(fillPersonaName("persona_name: {PERSONA_NAME}\nYou are {PERSONA_NAME}.", "  Layla ")).toBe("persona_name: Layla\nYou are Layla.");
  });

  it("keeps the token while the name is still blank", () => {
    expect(fillPersonaName(`x ${PERSONA_NAME_TOKEN} y`, "")).toBe("x {PERSONA_NAME} y");
    expect(fillPersonaName(`x ${PERSONA_NAME_TOKEN} y`, "   ")).toBe("x {PERSONA_NAME} y");
  });

  it("leaves text without the token untouched", () => {
    expect(fillPersonaName("plain role", "Layla")).toBe("plain role");
  });

  it("reports whether the token is present", () => {
    expect(hasPersonaNameToken("a {PERSONA_NAME} b")).toBe(true);
    expect(hasPersonaNameToken("a b")).toBe(false);
  });
});

describe("rolePreview", () => {
  const template = `---
persona_name: Yasir
role_type: execution
version: 1.1.0
---

# ROLE & IDENTITY
You are the **Lead Developer**. Your primary function is to write code.

# CORE OBJECTIVES
- Translate tickets into code.
`;

  it("drops the front matter and headings and reads the role as prose", () => {
    expect(rolePreview(template)).toBe("You are the Lead Developer. Your primary function is to write code. Translate tickets into code.");
  });

  it("leaves a plain role alone", () => {
    expect(rolePreview("You scout the market and report trends.")).toBe("You scout the market and report trends.");
  });

  it("does not mistake a horizontal rule further down for front matter", () => {
    expect(rolePreview("Be brief.\n\n---\n\nCite sources.")).toBe("Be brief. --- Cite sources.");
  });
});
