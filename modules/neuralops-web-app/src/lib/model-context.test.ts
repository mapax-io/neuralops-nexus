import { describe, expect, it } from "vitest";
import { DEFAULT_CONTEXT_WINDOW, defaultContextWindow } from "./model-context";

describe("defaultContextWindow", () => {
  it("knows the common families by bare model id", () => {
    expect(defaultContextWindow("openai", "gpt-4o-mini")).toBe(128_000);
    expect(defaultContextWindow("openai", "gpt-4.1")).toBe(1_047_576);
    expect(defaultContextWindow("openai", "o3-mini")).toBe(200_000);
    expect(defaultContextWindow("anthropic", "claude-sonnet-5")).toBe(200_000);
    expect(defaultContextWindow("anthropic", "claude-haiku-4-5-20251001")).toBe(200_000);
    expect(defaultContextWindow("google", "gemini-2.0-flash")).toBe(1_048_576);
    expect(defaultContextWindow("google", "gemini-1.5-pro")).toBe(2_097_152);
    expect(defaultContextWindow("ollama", "llama3")).toBe(8_192);
    expect(defaultContextWindow("ollama", "llama3.1:8b")).toBe(131_072);
    expect(defaultContextWindow("ollama", "qwen2.5-coder")).toBe(32_768);
  });

  it("matches by the id alone for compatible endpoints, case-insensitively", () => {
    expect(defaultContextWindow("openai_compatible", "GPT-4o")).toBe(128_000);
    expect(defaultContextWindow("openai_compatible", "deepseek-r1")).toBe(131_072);
  });

  it("falls back to the server default for anything unknown or blank", () => {
    expect(DEFAULT_CONTEXT_WINDOW).toBe(8_192);
    expect(defaultContextWindow("openai", "my-custom-finetune")).toBe(8_192);
    expect(defaultContextWindow("openai", "")).toBe(8_192);
  });
});
