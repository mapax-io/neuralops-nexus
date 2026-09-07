import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResetPasswordForm } from "./reset-password-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));
const getSession = vi.fn();
const updateUser = vi.fn();
vi.mock("@/lib/supabase", () => ({ supabase: () => ({ auth: { getSession, updateUser } }) }));

beforeEach(() => {
  push.mockReset();
  getSession.mockReset();
  updateUser.mockReset();
});

describe("ResetPasswordForm", () => {
  it("without a recovery session it explains and points back to the sign-in page instead of showing a doomed form", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    render(<ResetPasswordForm />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/link from your reset email/i);
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute("href", "/login");
  });

  it("with the recovery session it sets the password and moves on to the servers", async () => {
    getSession.mockResolvedValue({ data: { session: { user: { id: "u1" } } } });
    updateUser.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await user.type(await screen.findByLabelText(/^new password/i), "secret12");
    await user.type(screen.getByLabelText(/confirm password/i), "secret12");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith({ password: "secret12" }));
    expect(push).toHaveBeenCalledWith("/servers");
  });

  it("checks length and match before calling the identity provider, and translates a lost session", async () => {
    getSession.mockResolvedValue({ data: { session: { user: { id: "u1" } } } });
    updateUser.mockResolvedValue({ error: { message: "Auth session missing!" } });
    const user = userEvent.setup();
    render(<ResetPasswordForm />);
    await user.type(await screen.findByLabelText(/^new password/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/at least 8/i);
    expect(updateUser).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText(/^new password/i));
    await user.type(screen.getByLabelText(/^new password/i), "secret12");
    await user.clear(screen.getByLabelText(/confirm password/i));
    await user.type(screen.getByLabelText(/confirm password/i), "secret12");
    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/link has expired or was already used/i);
  });
});
