import { describe, expect, it } from "vitest";
import { fillPersonaName, hasPersonaNameToken, PERSONA_NAME_TOKEN } from "./persona-template";

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
