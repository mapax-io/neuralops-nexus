import { describe, expect, it } from "vitest";
import { CAPABILITIES, DEFAULT_CAPABILITY_KEYS, capabilityLabels, defaultCapabilityConfig, formatCapabilityConfig, parseCapabilityConfig } from "./mcp-capabilities";

describe("capability catalogue", () => {
  it("uses the worker's capability names as keys — every key is unique and non-empty", () => {
    const keys = CAPABILITIES.map((c) => c.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.every((k) => k.trim().length > 0)).toBe(true);
    // The four every project is provisioned with are in the catalogue.
    for (const k of DEFAULT_CAPABILITY_KEYS) expect(keys).toContain(k);
  });

  it("builds the default config for the project four, with the template's defaults", () => {
    const cfg = defaultCapabilityConfig();
    expect(Object.keys(cfg)).toEqual(["filesystem", "shell", "web_search", "web_fetch"]);
    expect(cfg.shell).toMatchObject({ cwd: ".", allow_interactive: true, default_timeout: 30, max_output_chars: 50000 });
    expect(cfg.web_search).toEqual({ local: "duckduckgo" });
    expect(cfg.filesystem.protected_patterns).toContain(".env");
    // Fresh copies — editing one row's defaults must never leak into the next.
    (cfg.filesystem.protected_patterns as string[]).push("x");
    expect(defaultCapabilityConfig().filesystem.protected_patterns).not.toContain("x");
  });

  it("labels a row's capabilities in catalogue order and keeps unknown keys verbatim", () => {
    expect(capabilityLabels({ web_fetch: {}, filesystem: {}, "Brand New": { a: 1 } })).toEqual(["Filesystem", "Web fetch", "Brand New"]);
    expect(capabilityLabels(null)).toEqual([]);
  });

  it("parses the wire shape and rejects anything that is not name → settings object", () => {
    expect(parseCapabilityConfig("")).toEqual({ value: {} });
    expect(parseCapabilityConfig('{"web_search": {"local": "brave"}}')).toEqual({ value: { web_search: { local: "brave" } } });
    expect(parseCapabilityConfig("[1]").error).toMatch(/JSON object/);
    expect(parseCapabilityConfig('{"shell": "yes"}').error).toMatch(/"shell" must map to a settings object/);
    expect(parseCapabilityConfig("{ nope").error).toMatch(/JSON object/);
  });

  it("formats an empty config as an empty editor, not {}", () => {
    expect(formatCapabilityConfig({})).toBe("");
    expect(formatCapabilityConfig({ planning: {} })).toBe(JSON.stringify({ planning: {} }, null, 2));
  });
});
