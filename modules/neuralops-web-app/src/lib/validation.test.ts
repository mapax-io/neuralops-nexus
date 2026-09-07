import { describe, expect, it } from "vitest";
import { validateEmail, validateMentionName, validateName, validateNumber, validateUrl } from "./validation";

describe("validateName", () => {
  it("accepts readable names with safe separators", () => {
    expect(validateName("Customer Research")).toBeNull();
    expect(validateName("Q4 Launch (2026)")).toBeNull();
    expect(validateName("Ops & Infra")).toBeNull();
  });
  it("rejects empty, too long, and special characters", () => {
    expect(validateName("  ")).toMatch(/enter a name/i);
    expect(validateName("a".repeat(81))).toMatch(/under 80/i);
    for (const bad of ["hi<script>", "a/b", 'say "hi"', "x{y}", "a\\b", "тест;"]) {
      expect(validateName(bad)).toMatch(/special characters/i);
    }
  });
  it("enforces uniqueness but excludes the value being edited", () => {
    expect(validateName("Design", { existing: ["design", "Ops"] })).toMatch(/already exists/i);
    expect(validateName("Design", { existing: ["design"], current: "Design" })).toBeNull();
  });
});

describe("validateMentionName", () => {
  it("accepts @-mentionable handles only", () => {
    expect(validateMentionName("Nova")).toBeNull();
    expect(validateMentionName("code_bot_2")).toBeNull();
  });
  it("rejects spaces, punctuation, and reserved words", () => {
    expect(validateMentionName("My Bot")).toMatch(/underscores only/i);
    expect(validateMentionName("bot!")).toMatch(/underscores only/i);
    expect(validateMentionName("session", { reserved: new Set(["session"]) })).toMatch(/reserved/i);
  });
});

describe("validateUrl", () => {
  it("accepts the schemes the caller names, and says which ones it wanted", () => {
    expect(validateUrl("wss://tools.example.com/mcp", { schemes: ["ws:", "wss:"] })).toBeNull();
    expect(validateUrl("https://tools.example.com/mcp", { schemes: ["ws:", "wss:"] })).toBe("The URL must start with ws:// or wss://.");
    expect(validateUrl("wss://tools.example.com/mcp")).toBe("The URL must start with http:// or https://.");
    expect(validateUrl("tools.example.com", { schemes: ["ws:", "wss:"] })).toBe("Enter a valid URL (including ws:// or wss://).");
  });

  it("accepts http(s) URLs", () => {
    expect(validateUrl("https://example.com")).toBeNull();
    expect(validateUrl("http://localhost:8080/mcp")).toBeNull();
  });
  it("rejects junk and non-http protocols", () => {
    expect(validateUrl("not a url")).toMatch(/valid URL/i);
    expect(validateUrl("ftp://x.com")).toMatch(/http/i);
  });
  it("allows empty when not required", () => {
    expect(validateUrl("", { required: false })).toBeNull();
    expect(validateUrl("")).toMatch(/enter/i);
  });
});

describe("validateNumber", () => {
  it("enforces range and integer", () => {
    expect(validateNumber(5, { min: 1, max: 10 })).toBeNull();
    expect(validateNumber(0, { min: 1 })).toMatch(/at least 1/i);
    expect(validateNumber(2.5, { integer: true })).toMatch(/whole number/i);
    expect(validateNumber("", {})).toMatch(/enter/i);
  });
});

describe("validateEmail", () => {
  it("checks basic shape", () => {
    expect(validateEmail("a@b.co")).toBeNull();
    expect(validateEmail("nope")).toMatch(/valid email/i);
  });
});
