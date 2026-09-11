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

// The @name a user typed as a pill in the composer must read as a pill in the
// message it became — and an unknown name must stay plain, exactly as the
// composer leaves it.
describe("MessageItem — @mentions render as chips", () => {
  const known = {
    mentions: new Set(["pv12"]),
    self: new Set(["project1_pv"]),
    humans: new Set(["tahayabali2"]),
    commands: new Set(["swarm"]),
  };

  const say = (content: string, withKnown = true) =>
    render(<MessageItem message={{ ...base, content }} known={withKnown ? known : undefined} />);

  it("chips a known persona", () => {
    const { container } = say("@pv12 hi");
    const pill = container.querySelector(".nx-mention-pill");
    expect(pill).toHaveTextContent("@pv12");
    expect(container).toHaveTextContent("@pv12 hi"); // text is unchanged
  });

  it("leaves an unknown name as plain text", () => {
    const { container } = say("@nobody hi");
    expect(container.querySelector(".nx-mention-pill")).toBeNull();
    expect(container).toHaveTextContent("@nobody hi");
  });

  it("distinguishes you from a teammate", () => {
    const { container } = say("@project1_pv and @tahayabali2");
    expect(container.querySelector(".nx-self-pill")).toHaveTextContent("@project1_pv");
    expect(container.querySelector(".nx-human-pill")).toHaveTextContent("@tahayabali2");
  });

  it("stays plain until the known-set has loaded", () => {
    const { container } = say("@pv12 hi", false);
    expect(container.querySelector(".nx-mention-pill")).toBeNull();
    expect(container).toHaveTextContent("@pv12 hi");
  });

  it("does not chip a mention inside code", () => {
    const { container } = say("`@pv12`");
    expect(container.querySelector(".nx-mention-pill")).toBeNull();
    expect(container.querySelector("code")).toHaveTextContent("@pv12");
  });
});
