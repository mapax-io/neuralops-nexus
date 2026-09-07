import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { CapabilityEditor } from "./capability-editor";
import { defaultCapabilityConfig } from "@/lib/mcp-capabilities";

describe("CapabilityEditor — the checklist", () => {
  it("ticks the capabilities present in the value and counts them", () => {
    render(<CapabilityEditor idPrefix="t" value={defaultCapabilityConfig()} onChange={() => {}} />);
    expect(screen.getByLabelText(/^Filesystem/)).toBeChecked();
    expect(screen.getByLabelText(/^Shell/)).toBeChecked();
    expect(screen.getByLabelText(/^Web search/)).toBeChecked();
    expect(screen.getByLabelText(/^Web fetch/)).toBeChecked();
    expect(screen.getByLabelText(/^Thinking/)).not.toBeChecked();
    expect(screen.getByText("(4 on)")).toBeInTheDocument();
  });

  it("ticking adds the capability with the template's defaults; unticking removes the key", () => {
    const onChange = vi.fn();
    render(<CapabilityEditor idPrefix="t" value={{ Planning: {} }} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText(/^Thinking/));
    expect(onChange).toHaveBeenLastCalledWith({ Planning: {}, Thinking: { effort: "medium" } });
    fireEvent.click(screen.getByLabelText(/^Planning/));
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it("edits a capability's settings in place, keeping fields it does not know", () => {
    const onChange = vi.fn();
    render(<CapabilityEditor idPrefix="t" value={{ Shell: { cwd: ".", allowed_commands: ["ls"], denied_commands: [], extra: 1 } }} onChange={onChange} />);
    fireEvent.click(within(screen.getByRole("group", { name: "Allowed commands" })).getByRole("button", { name: "cat" }));
    expect(onChange).toHaveBeenLastCalledWith({ Shell: { cwd: ".", allowed_commands: ["ls", "cat"], denied_commands: [], extra: 1 } });
    fireEvent.change(screen.getByLabelText("Working folder"), { target: { value: "src" } });
    expect(onChange).toHaveBeenLastCalledWith({ Shell: { cwd: "src", allowed_commands: ["ls"], denied_commands: [], extra: 1 } });
  });

  it("splits glob lists one per line and reads the thinking effort from a select", () => {
    const onChange = vi.fn();
    render(<CapabilityEditor idPrefix="t" value={{ Filesystem: { root_dir: "." }, Thinking: { effort: "low" } }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/denied globs/i), { target: { value: "*.pem\n secrets/**" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ Filesystem: { root_dir: ".", denied_patterns: ["*.pem", "secrets/**"] } }));
    expect(screen.getByLabelText("Effort")).toHaveValue("low");
    fireEvent.change(screen.getByLabelText("Effort"), { target: { value: "high" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ Thinking: { effort: "high" } }));
  });

  it("lists a capability the catalogue does not know and keeps it verbatim", () => {
    const onChange = vi.fn();
    render(<CapabilityEditor idPrefix="t" value={{ "Brand New": { a: 1 } }} onChange={onChange} />);
    expect(screen.getByLabelText(/^Brand New/)).toBeChecked();
    fireEvent.click(screen.getByLabelText(/^Brand New/));
    expect(onChange).toHaveBeenLastCalledWith({});
  });
});

describe("CapabilityEditor — JSON view", () => {
  it("shows the whole config, applies valid edits, and blocks on invalid text", () => {
    const onChange = vi.fn();
    const onError = vi.fn();
    render(<CapabilityEditor idPrefix="t" value={{ "Web Fetch": { local: true } }} onChange={onChange} onError={onError} />);
    fireEvent.click(screen.getByRole("button", { name: /edit as json/i }));
    const area = screen.getByLabelText("Capabilities JSON") as HTMLTextAreaElement;
    expect(area.value).toBe(JSON.stringify({ "Web Fetch": { local: true } }, null, 2));
    fireEvent.change(area, { target: { value: '{"Web Fetch": {"local": false}, "Memory": {}}' } });
    expect(onChange).toHaveBeenLastCalledWith({ "Web Fetch": { local: false }, Memory: {} });
    expect(onError).toHaveBeenLastCalledWith(null);
    fireEvent.change(area, { target: { value: "{ broken" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/JSON object/);
    expect(onError).toHaveBeenLastCalledWith(expect.stringMatching(/JSON object/));
    // Cannot leave the JSON view on broken text — that would silently revert.
    fireEvent.click(screen.getByRole("button", { name: /back to the list/i }));
    expect(screen.getByLabelText("Capabilities JSON")).toBeInTheDocument();
  });
});
