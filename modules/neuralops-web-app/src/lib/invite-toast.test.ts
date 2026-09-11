import { beforeEach, describe, expect, it, vi } from "vitest";

const success = vi.fn((..._a: unknown[]): number => 42);
const dismiss = vi.fn((..._a: unknown[]): void => undefined);
const error = vi.fn((..._a: unknown[]): void => undefined);
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => success(...a), dismiss: (...a: unknown[]) => dismiss(...a), error: (...a: unknown[]) => error(...a) } }));
const copyText = vi.fn((..._a: unknown[]): Promise<boolean> => Promise.resolve(true));
vi.mock("@/lib/browser", () => ({ copyText: (...a: unknown[]) => copyText(...a), randomId: () => "id" }));

import { notifyInvite } from "./invite-toast";

const ctx = { serverUrl: "https://nexus.acme.io", appOrigin: "https://app.example", companyName: "Acme" };
type Opts = { description?: string; duration?: number; closeButton?: boolean; action?: { label: string; onClick: (e: { preventDefault: () => void }) => void } };

beforeEach(() => {
  success.mockClear();
  dismiss.mockClear();
  error.mockClear();
  copyText.mockClear();
});

describe("notifyInvite — one toast per outcome, and never a word about email", () => {
  it("an existing member: the server's message, nothing to pass on", () => {
    notifyInvite({ email: "sam@acme.io", message: "sam@acme.io added to this server." }, ctx);
    expect(success).toHaveBeenCalledWith("sam@acme.io added to this server.");
  });

  // Whether the server emailed them, could not, sent a sign-in link instead,
  // or predates the flag entirely: the way in is the same, so the toast is.
  it.each([
    ["the server emailed them", { is_new_user: true, email_sent: true }],
    ["the server could not email them", { is_new_user: true, email_sent: false, email_note: "This server is not set up to send email -- no SUPABASE_SERVICE_KEY is configured." }],
    ["a sign-in email went instead", { is_new_user: true, email_sent: true, email_note: "They already had a NeuralOps account, so a sign-in email was sent instead." }],
    ["a server that predates the flag", { expires_at: "2026-09-14T00:00:00Z" }],
  ])("a pending invite (%s): they are invited, the steps to pass on", (_, outcome) => {
    notifyInvite({ email: "sam@acme.io", ...outcome }, ctx);
    const [title, opts] = success.mock.calls[0] as unknown as [string, Opts];
    expect(title).toBe("sam@acme.io is invited.");
    expect(opts.description).toMatch(/sign up with that exact address, add this server, and they're in/i);
    expect(`${title} ${opts.description}`).not.toMatch(/e-?mail/i);
    expect(opts.action?.label).toBe("Copy steps");
  });
});

describe("notifyInvite — the pending toast stays until they copy or close it", () => {
  const pending = () => {
    notifyInvite({ email: "sam@acme.io", is_new_user: true }, ctx);
    return success.mock.calls[0] as unknown as [string, Opts];
  };

  it("never times out and offers a close control", () => {
    const [, opts] = pending();
    expect(opts.duration).toBe(Infinity);
    expect(opts.closeButton).toBe(true);
  });

  it("Copy steps copies the steps and only then dismisses the toast", async () => {
    copyText.mockResolvedValue(true);
    const [, opts] = pending();
    const preventDefault = vi.fn();
    opts.action!.onClick({ preventDefault });
    expect(preventDefault).toHaveBeenCalled(); // sonner would otherwise close it on the click alone
    expect(copyText).toHaveBeenCalledWith(expect.stringMatching(/create an account at https:\/\/app\.example\/login with sam@acme\.io/i));
    await vi.waitFor(() => expect(dismiss).toHaveBeenCalledWith(42));
    expect(success).toHaveBeenLastCalledWith("Steps copied — send them along.");
  });

  it("keeps the toast when the copy fails, so nothing is lost", async () => {
    copyText.mockResolvedValue(false);
    const [, opts] = pending();
    opts.action!.onClick({ preventDefault: vi.fn() });
    await vi.waitFor(() => expect(error).toHaveBeenCalledWith("Couldn't copy the steps."));
    expect(dismiss).not.toHaveBeenCalled();
  });
});
