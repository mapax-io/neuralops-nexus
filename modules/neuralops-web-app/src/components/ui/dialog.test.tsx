import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ConfirmDialog, Dialog } from "./dialog";

// Regression: a consumer that recreates onClose on every keystroke (the
// common inline-arrow pattern) must not make the dialog steal focus from the
// field being typed in.
function TypingHarness() {
  const [value, setValue] = useState("");
  const close = () => setValue(value); // new identity on every render
  return (
    <Dialog open onClose={close} title="New project">
      <input aria-label="Name" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
    </Dialog>
  );
}

describe("Dialog", () => {
  it("keeps focus in the input while typing, even with an unstable onClose", async () => {
    const user = userEvent.setup();
    render(<TypingHarness />);
    const input = screen.getByLabelText("Name");
    await user.click(input);
    await user.keyboard("Quarterly Review");
    expect(input).toHaveFocus();
    expect(input).toHaveValue("Quarterly Review");
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} title="Test">
        <p>body</p>
      </Dialog>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("lets Tab move through a STACKED dialog instead of trapping on its first control", async () => {
    // Regression: with two dialogs open, both focus traps used to fight —
    // the host yanked focus out of the nested panel on every Tab, so focus
    // never got past the nested dialog's first focusable (its Close button).
    const user = userEvent.setup();
    render(
      <>
        <Dialog open onClose={() => {}} title="Host">
          <input aria-label="Host field" />
        </Dialog>
        <Dialog open onClose={() => {}} title="Nested">
          <input aria-label="First" />
          <input aria-label="Second" />
        </Dialog>
      </>,
    );
    screen.getByLabelText("First").focus();
    await user.tab();
    expect(screen.getByLabelText("Second")).toHaveFocus();
    // And the trap still cycles within the nested panel, never into the host.
    const nested = screen.getByRole("dialog", { name: "Nested" });
    await user.tab();
    expect(within(nested).getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("Escape closes only the topmost stacked dialog", async () => {
    const user = userEvent.setup();
    const closeHost = vi.fn();
    const closeNested = vi.fn();
    render(
      <>
        <Dialog open onClose={closeHost} title="Host"><p>host</p></Dialog>
        <Dialog open onClose={closeNested} title="Nested"><p>nested</p></Dialog>
      </>,
    );
    await user.keyboard("{Escape}");
    expect(closeNested).toHaveBeenCalledTimes(1);
    expect(closeHost).not.toHaveBeenCalled();
  });

  it("renders title, description and icon area", () => {
    render(
      <Dialog open onClose={() => {}} title="New channel" description="Channels split a project by subject.">
        <p>body</p>
      </Dialog>,
    );
    expect(screen.getByRole("dialog", { name: "New channel" })).toBeInTheDocument();
    expect(screen.getByText(/split a project/)).toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  it("confirms and cancels", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <ConfirmDialog open onClose={onClose} onConfirm={onConfirm} title="Remove server?" body={<p>Sure?</p>} confirmLabel="Remove" />,
    );
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(onConfirm).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });
});
