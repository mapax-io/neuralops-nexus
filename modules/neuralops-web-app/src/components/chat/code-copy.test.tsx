import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageItem } from "./message-item";
import type { UiMessage } from "@/lib/realtime/message-store";

const base: Omit<UiMessage, "content" | "renderAs"> = {
  id: "m1", outputType: "text", senderName: "Dev", senderId: "p1", senderAvatar: null, senderType: "persona",
  personaId: "pe1", sequence: 1, createdAt: new Date().toISOString(), isSystem: false, isStreaming: false,
  isError: false, isStalled: false, lastActivity: 0,
};
const msg = (content: string, renderAs = "text"): UiMessage => ({ ...base, content, renderAs });

const writeText = vi.fn();
beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});

describe("markdown code blocks — copy", () => {
  it("gives every fenced block its own copy button (inline code gets none) and copies exactly that block", () => {
    render(<MessageItem message={msg("Run this:\n\n```ts\nconst a = 1;\n```\n\nthen `inline` and\n\n```\necho hi\n```")} />);
    const buttons = screen.getAllByRole("button", { name: /copy code/i });
    expect(buttons).toHaveLength(2);
    // The block's header names its language (a bare fence reads "code").
    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("code")).toBeInTheDocument();
    fireEvent.click(buttons[0]);
    expect(writeText).toHaveBeenCalledWith("const a = 1;"); // no trailing newline
    fireEvent.click(buttons[1]);
    expect(writeText).toHaveBeenLastCalledWith("echo hi");
  });

  it("keeps the dedicated code output's header copy button as it was", () => {
    render(<MessageItem message={msg("print(1)", "code")} />);
    fireEvent.click(screen.getByRole("button", { name: /copy to clipboard/i }));
    expect(writeText).toHaveBeenCalledWith("print(1)");
    expect(screen.queryByRole("button", { name: /copy code/i })).not.toBeInTheDocument();
  });
});
