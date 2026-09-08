import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MissingEmailNotice } from "./missing-email-notice";

describe("MissingEmailNotice — a session without an email cannot connect anywhere", () => {
  it("says why, what to do for a GitHub sign-in, and offers sign-out", () => {
    const onSignOut = vi.fn();
    render(<MissingEmailNotice onSignOut={onSignOut} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/no email address/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/github/i);
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(onSignOut).toHaveBeenCalled();
  });
});
