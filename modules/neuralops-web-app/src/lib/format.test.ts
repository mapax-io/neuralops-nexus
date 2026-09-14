import { describe, expect, it } from "vitest";
import { formatTokens, formatUsd } from "./format";

describe("formatTokens", () => {
  it("keeps small counts exact and compacts thousands and millions", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(1_200)).toBe("1.2k");
    expect(formatTokens(48_000)).toBe("48k");
    expect(formatTokens(1_250_000)).toBe("1.3M");
    expect(formatTokens(2_000_000_000)).toBe("2B");
  });
});

describe("formatUsd", () => {
  it("shows cents, and more digits only when the amount is below a cent", () => {
    expect(formatUsd(3.4)).toBe("$3.40");
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(0.0021)).toBe("$0.0021");
    expect(formatUsd(1234.5)).toBe("$1,234.50");
  });
});
