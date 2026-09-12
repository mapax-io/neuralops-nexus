import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ConfirmDialog, Dialog, DialogSection } from "./dialog";

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

  it("yields Escape to an open combobox inside it: the press is the list's to close, not the dialog's", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    function Harness() {
      const [expanded, setExpanded] = useState(true);
      return (
        <Dialog open onClose={onClose} title="Register model">
          <input aria-label="Model id" role="combobox" aria-expanded={expanded} aria-controls="suggestions" autoFocus onKeyDown={(e) => { if (e.key === "Escape") setExpanded(false); }} />
          <ul id="suggestions" role="listbox" hidden={!expanded} />
        </Dialog>
      );
    }
    render(<Harness />);
    const box = screen.getByRole("combobox", { name: "Model id" });
    expect(box).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    expect(box).toHaveAttribute("aria-expanded", "false");
    // Closed list: the next Escape is the dialog's again.
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("still closes on Escape from an expanded section toggle — only comboboxes own the key", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} title="Invite">
        <button aria-expanded="true" autoFocus>Engineering</button>
      </Dialog>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps the pinned header to icon, title and close; the description opens the scrolling body", () => {
    render(
      <Dialog open onClose={() => {}} title="New channel" description="Channels split a project by subject." icon={<span data-testid="ic" />}>
        <p>body</p>
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "New channel" });
    const desc = screen.getByText(/split a project/);
    // Still the dialog's description for assistive tech…
    expect(dialog).toHaveAttribute("aria-describedby", desc.id);
    // …but it lives in the scroll container, not next to the title.
    expect(desc.closest(".overflow-y-auto")).not.toBeNull();
    const header = screen.getByRole("heading", { name: "New channel" }).parentElement!;
    expect(header).not.toContainElement(desc);
    expect(header).toContainElement(screen.getByTestId("ic"));
    expect(header).toContainElement(screen.getByRole("button", { name: "Close" }));
    // The body reads description first, then the content.
    expect(desc.compareDocumentPosition(screen.getByText("body")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("tints the icon chip by tone — neutral by default", () => {
    const { rerender } = render(<Dialog open onClose={() => {}} title="T" icon={<span data-testid="ic" />}><p>b</p></Dialog>);
    expect(screen.getByTestId("ic").parentElement!.className).toMatch(/text-ink2/);
    rerender(<Dialog open onClose={() => {}} title="T" icon={<span data-testid="ic" />} tone="accent"><p>b</p></Dialog>);
    expect(screen.getByTestId("ic").parentElement!.className).toMatch(/text-accent/);
    rerender(<Dialog open onClose={() => {}} title="T" icon={<span data-testid="ic" />} tone="info"><p>b</p></Dialog>);
    expect(screen.getByTestId("ic").parentElement!.className).toMatch(/text-info/);
  });
});

describe("DialogSection", () => {
  it("heads each group, shows the hint, divides sections after the first, and never shadows a field label", () => {
    render(
      <Dialog open onClose={() => {}} title="T">
        <DialogSection title="Identity" hint="Who it is."><input aria-label="Name" /></DialogSection>
        <DialogSection title="Name"><input aria-label="Key" /></DialogSection>
      </Dialog>,
    );
    const first = screen.getByRole("heading", { level: 3, name: "Identity" }).closest("section")!;
    const second = screen.getByRole("heading", { level: 3, name: "Name" }).closest("section")!;
    expect(first).toContainElement(screen.getByLabelText("Name")); // the input — a section titled "Name" is not a label
    expect(within(first).getByText("Who it is.")).toBeInTheDocument();
    expect(second).toContainElement(screen.getByLabelText("Key"));
    expect(first.className).toMatch(/first:border-t-0/);
    expect(second.className).toMatch(/border-t/);
  });

  it("form dialogs are 4xl wide; confirmations stay narrow", () => {
    const { rerender } = render(<Dialog open onClose={() => {}} title="Form"><p>b</p></Dialog>);
    expect(screen.getByRole("dialog").className).toMatch(/max-w-4xl/);
    rerender(<Dialog open onClose={() => {}} title="Form" size="sm"><p>b</p></Dialog>);
    expect(screen.getByRole("dialog").className).toMatch(/max-w-md/);
  });
});

describe("ConfirmDialog", () => {
  it("colours its icon by tone: red for destructive, amber for a cautious confirm", () => {
    const { rerender } = render(<ConfirmDialog open onClose={() => {}} onConfirm={() => {}} title="Remove?" body="x" confirmLabel="Remove" />);
    const chip = () => screen.getByRole("dialog").querySelector("h2")!.parentElement!.querySelector("span")!;
    expect(chip().className).toMatch(/text-crit/);
    rerender(<ConfirmDialog open onClose={() => {}} onConfirm={() => {}} title="Sign out?" body="x" confirmLabel="Sign out" tone="neutral" />);
    expect(chip().className).toMatch(/text-warn/);
  });

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
