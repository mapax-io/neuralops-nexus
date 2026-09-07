import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageItem } from "./message-item";
import type { UiMessage } from "@/lib/realtime/message-store";

const base: UiMessage = {
  id: "m1", content: "", renderAs: "text", outputType: "text", senderName: "Layla", senderId: "p1", senderAvatar: null,
  senderType: "persona", personaId: "pe1", sequence: 1, createdAt: new Date().toISOString(), isSystem: false,
  isStreaming: false, isError: false, isStalled: false, lastActivity: 0,
};

// After upstream #101 nucleus saves output_type "text" next to a marker-derived
// render_as. The renderer must follow render_as, not output_type.
describe("MessageItem — renderer follows render_as", () => {
  it("frames html output even when output_type is text", () => {
    const { container } = render(<MessageItem message={{ ...base, content: "<html><body>chart</body></html>", renderAs: "html" }} />);
    expect(container.querySelector("iframe")).not.toBeNull();
    expect(screen.queryByText(/composing/i)).not.toBeInTheDocument();
    expect(screen.queryByText("<html><body>chart</body></html>")).not.toBeInTheDocument();
  });

  it("renders terminal output as a terminal block under the same shape", () => {
    const { container } = render(<MessageItem message={{ ...base, content: "$ ls\nREADME.md", renderAs: "terminal" }} />);
    expect(container.querySelector("pre")).not.toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
  });
});
