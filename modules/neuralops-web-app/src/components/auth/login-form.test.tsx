import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "./login-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const signInWithPassword = vi.fn();
const signUp = vi.fn();
const resetPasswordForEmail = vi.fn();
const signInWithOAuth = vi.fn();
vi.mock("@/lib/supabase", () => ({
  supabase: () => ({ auth: { signInWithPassword, signUp, signInWithOAuth, resetPasswordForEmail } }),
}));

beforeEach(() => {
  push.mockReset();
  signInWithPassword.mockReset();
  signUp.mockReset();
  signInWithOAuth.mockReset();
});

describe("LoginForm", () => {
  it("marks email and password as required", () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeRequired();
    expect(screen.getByLabelText(/password/i)).toBeRequired();
  });

  it("validates email and password before calling the identity provider", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(screen.getByText(/enter your password/i)).toBeInTheDocument();
    expect(signInWithPassword).not.toHaveBeenCalled();
  });

  // Sign-in must never length-check (existing accounts may predate any
  // policy); the 8-character rule applies only where a password is being set.
  it("length-checks the password at sign-up but not at sign-in", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /create an account/i }));
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.type(screen.getByLabelText(/password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument();
  });

  it("signs in and moves to server selection", async () => {
    signInWithPassword.mockResolvedValue({ data: { session: { access_token: "t" } }, error: null });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.type(screen.getByLabelText(/password/i), "secret1");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(signInWithPassword).toHaveBeenCalledWith({ email: "a@b.co", password: "secret1" });
    expect(push).toHaveBeenCalledWith("/servers");
  });

  it("switches to sign-up mode and handles the confirm-email flow", async () => {
    signUp.mockResolvedValue({ data: { session: null }, error: null });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /create an account/i }));
    await user.type(screen.getByLabelText(/email/i), "new@b.co");
    await user.type(screen.getByLabelText(/password/i), "secret12"); // sign-up requires 8+
    await user.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("sends a reset link in forgot mode without demanding a password", async () => {
    resetPasswordForEmail.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /forgot password/i }));
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByText(/check your email for a reset link/i)).toBeInTheDocument();
    expect(resetPasswordForEmail).toHaveBeenCalledWith("a@b.co", expect.anything());
  });

  it("explains a disabled GitHub provider instead of echoing the raw error", async () => {
    signInWithOAuth.mockResolvedValue({ error: new Error("Unsupported provider: provider is not enabled") });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /continue with github/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/isn't switched on/i);
    expect(signInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "github" }),
    );
  });

  it("passes through unexpected GitHub sign-in errors verbatim", async () => {
    signInWithOAuth.mockResolvedValue({ error: new Error("Network request failed") });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /continue with github/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/network request failed/i);
  });

  it("surfaces identity-provider errors", async () => {
    signInWithPassword.mockResolvedValue({ data: {}, error: new Error("Invalid login credentials") });
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.type(screen.getByLabelText(/password/i), "wrongpw");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid login/i);
  });
});
