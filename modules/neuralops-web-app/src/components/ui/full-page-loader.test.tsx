import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { FullPageLoader } from "./full-page-loader";

vi.mock("@/lib/auth/sign-out", () => ({ signOutOnThisDevice: vi.fn(() => Promise.resolve()) }));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("FullPageLoader — never a spinner without a way out", () => {
  it("is just the mark and the label at first", () => {
    render(<FullPageLoader />);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("after ten seconds says so and offers Reload and Sign out", async () => {
    const reload = vi.fn();
    const signOut = vi.fn(() => Promise.resolve());
    render(<FullPageLoader escape={{ reload, signOut }} />);
    act(() => { vi.advanceTimersByTime(9_900); });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(200); });
    expect(screen.getByText(/taking longer than usual/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(reload).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("does not fire the escape after it has gone away", () => {
    const { unmount } = render(<FullPageLoader />);
    unmount();
    expect(() => act(() => { vi.advanceTimersByTime(20_000); })).not.toThrow();
  });
});
