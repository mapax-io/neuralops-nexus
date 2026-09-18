import { describe, expect, it, vi } from "vitest";
import { createEvent, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { ChipInput } from "./chip-input";

function Host({ initial = [], onSubmit = () => {} }: { initial?: string[]; onSubmit?: () => void }) {
  const [value, setValue] = useState<string[]>(initial);
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
      <label htmlFor="globs">Denied globs</label>
      <ChipInput id="globs" label="Denied globs" value={value} onChange={setValue} placeholder="Type a glob and press Enter" />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </form>
  );
}
const input = () => screen.getByRole("textbox", { name: "Denied globs" });
const group = () => screen.getByRole("group", { name: "Denied globs" });
const value = () => JSON.parse(screen.getByTestId("value").textContent ?? "[]") as string[];

describe("ChipInput", () => {
  it("shows one chip per entry, each with its own remove control", () => {
    render(<Host initial={["*.pem", "secrets/**"]} />);
    expect(within(group()).getByText("*.pem")).toBeInTheDocument();
    expect(within(group()).getByText("secrets/**")).toBeInTheDocument();
    fireEvent.click(within(group()).getByRole("button", { name: "Remove *.pem" }));
    expect(value()).toEqual(["secrets/**"]);
    expect(input()).toHaveFocus(); // the removed chip's button is gone; typing continues in the field
  });

  it("Enter adds the typed entry as a chip and is always consumed, so it never submits the form around it", () => {
    const onSubmit = vi.fn();
    render(<Host onSubmit={onSubmit} />);
    fireEvent.change(input(), { target: { value: " *.log " } });
    const enter = createEvent.keyDown(input(), { key: "Enter" });
    fireEvent(input(), enter);
    expect(enter.defaultPrevented).toBe(true);
    expect(value()).toEqual(["*.log"]);
    expect(input()).toHaveValue("");
    const again = createEvent.keyDown(input(), { key: "Enter" });
    fireEvent(input(), again); // empty draft: nothing added, still consumed
    expect(again.defaultPrevented).toBe(true);
    expect(value()).toEqual(["*.log"]);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("a comma while typing splits off a chip; a pasted list becomes chips, one per line or comma", () => {
    render(<Host />);
    fireEvent.change(input(), { target: { value: "*.pem, *.key" } });
    expect(value()).toEqual(["*.pem"]);
    expect(input()).toHaveValue("*.key");
    // The input element drops newlines from a paste before onChange runs, so
    // the list is read from the paste event itself.
    fireEvent.paste(input(), { clipboardData: { getData: () => "secrets/**\n.env, *.bak\n" } });
    expect(value()).toEqual(["*.pem", "secrets/**", ".env", "*.bak"]);
    expect(input()).toHaveValue("*.key"); // what was being typed is untouched
    fireEvent.paste(input(), { clipboardData: { getData: () => "single" } });
    expect(value()).toEqual(["*.pem", "secrets/**", ".env", "*.bak"]); // one token: not intercepted
  });

  it("commits a pending draft on blur, so an entry typed right before Save is never lost", () => {
    render(<Host />);
    fireEvent.change(input(), { target: { value: "*.bak" } });
    fireEvent.blur(input());
    expect(value()).toEqual(["*.bak"]);
    expect(input()).toHaveValue("");
  });

  it("Backspace on an empty draft removes the last chip; with text it only edits the text", () => {
    render(<Host initial={["a", "b"]} />);
    fireEvent.change(input(), { target: { value: "c" } });
    fireEvent.keyDown(input(), { key: "Backspace" });
    expect(value()).toEqual(["a", "b"]);
    fireEvent.change(input(), { target: { value: "" } });
    fireEvent.keyDown(input(), { key: "Backspace" });
    expect(value()).toEqual(["a"]);
  });

  it("ignores blanks and duplicates, and never lets a draft start with a space", () => {
    render(<Host initial={["*.pem"]} />);
    fireEvent.change(input(), { target: { value: "  *.tmp" } });
    expect(input()).toHaveValue("*.tmp");
    fireEvent.change(input(), { target: { value: "*.pem" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    fireEvent.change(input(), { target: { value: "   " } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(value()).toEqual(["*.pem"]);
    expect(input()).toHaveValue("");
  });

  it("clicking anywhere in the box focuses the text field; the placeholder shows only while empty", () => {
    render(<Host />);
    expect(input()).toHaveAttribute("placeholder", "Type a glob and press Enter");
    fireEvent.pointerDown(group());
    expect(input()).toHaveFocus();
    fireEvent.change(input(), { target: { value: "x," } });
    expect(value()).toEqual(["x"]);
    expect(input()).not.toHaveAttribute("placeholder");
    input().blur();
    fireEvent.pointerDown(within(group()).getByText("x")); // a chip's text, not its remove button
    expect(input()).toHaveFocus();
  });
});
