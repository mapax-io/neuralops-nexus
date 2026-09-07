import { describe, expect, it } from "vitest";
import { inviteInstructions, isPendingInvite } from "./invite-copy";

describe("isPendingInvite — the server sends no email, so a pending invite needs the inviter to pass the steps on", () => {
  it("is pending when the server says the person is new, or when an expiry came back", () => {
    expect(isPendingInvite({ is_new_user: true })).toBe(true);
    expect(isPendingInvite({ expires_at: "2026-09-14T00:00:00Z" })).toBe(true);
    expect(isPendingInvite({ is_new_user: false, expires_at: null })).toBe(false);
    expect(isPendingInvite({})).toBe(false);
  });
});

describe("inviteInstructions — copy-ready steps for the invitee", () => {
  it("names the exact email, the sign-up address, the server address, and the expiry", () => {
    const text = inviteInstructions({ email: "sam@acme.io", appOrigin: "https://app.example", serverUrl: "https://nexus.acme.io", companyName: "Acme", expiresAt: "2026-09-14T09:00:00Z" });
    expect(text).toContain("Acme");
    expect(text).toContain("https://app.example/login");
    expect(text).toContain("sam@acme.io");
    expect(text).toContain("https://nexus.acme.io");
    expect(text).toMatch(/expires/i);
  });

  it("copes without a company name, server address or expiry", () => {
    const text = inviteInstructions({ email: "sam@acme.io", appOrigin: "https://app.example", serverUrl: null });
    expect(text).toContain("NeuralOps Nexus");
    expect(text).toContain("the server address");
    expect(text).not.toMatch(/expires/i);
  });
});
