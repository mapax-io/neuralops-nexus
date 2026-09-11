import { beforeEach, describe, expect, it, vi } from "vitest";

const success = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => success(...a), error: vi.fn() } }));
vi.mock("@/lib/browser", () => ({ copyText: vi.fn().mockResolvedValue(true), randomId: () => "id" }));

import { notifyInvite } from "./invite-toast";

const ctx = { serverUrl: "https://nexus.acme.io", appOrigin: "https://app.example", companyName: "Acme" };

beforeEach(() => success.mockClear());

describe("notifyInvite — one toast per outcome", () => {
  it("an existing member: the server's message, nothing to pass on", () => {
    notifyInvite({ email: "sam@acme.io", message: "sam@acme.io added to this server." }, ctx);
    expect(success).toHaveBeenCalledWith("sam@acme.io added to this server.");
  });

  it("a pending invite the server emailed: says so, no steps", () => {
    notifyInvite({ email: "sam@acme.io", is_new_user: true, email_sent: true }, ctx);
    const [title, opts] = success.mock.calls[0] as [string, { description?: string; action?: unknown }];
    expect(title).toMatch(/invitation email sent to sam@acme.io/i);
    expect(opts.description).toMatch(/set a password/i);
    expect(opts.action).toBeUndefined();
  });

  it("a pending invite the server emailed WITH a note: the note is the explanation (a sign-in email went instead)", () => {
    notifyInvite({ email: "a@b.test", is_new_user: true, email_sent: true, email_note: "They already had a NeuralOps account, so a sign-in email was sent instead." }, ctx);
    expect(success).toHaveBeenCalledWith("Invitation email sent to a@b.test.", expect.objectContaining({ description: expect.stringMatching(/sign-in email was sent instead/) }));
  });

  it("a pending invite with no email: steps to copy, with the server's note when it gave one", () => {
    notifyInvite({ email: "sam@acme.io", is_new_user: true, email_sent: false, email_note: "They already have a NeuralOps account, so no email was sent." }, ctx);
    const [title, opts] = success.mock.calls[0] as [string, { description?: string; action?: { label: string } }];
    expect(title).toMatch(/no email went out/i);
    expect(opts.description).toMatch(/already have a NeuralOps account/i);
    expect(opts.action?.label).toBe("Copy steps");
  });

  it("a pending invite from a server that predates the flag: steps with the default description", () => {
    notifyInvite({ email: "sam@acme.io", expires_at: "2026-09-14T00:00:00Z" }, ctx);
    const [, opts] = success.mock.calls[0] as [string, { description?: string }];
    expect(opts.description).toMatch(/create an account with that exact address/i);
  });
});
