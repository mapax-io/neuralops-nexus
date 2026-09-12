import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { UiMessage } from "@/lib/realtime/message-store";
import { MessageList } from "./message-list";

// selfId = "me" — distinguishes own sends (always follow to bottom) from others.
vi.mock("@/stores/connection.store", () => ({
  useConnectionStore: (sel: (s: { connection: { nucleusUserId: string } }) => unknown) =>
    sel({ connection: { nucleusUserId: "me" } }),
}));

const msg = (id: string, senderId = "other"): UiMessage => ({
  id, content: id, renderAs: "text", outputType: "text",
  senderName: senderId, senderId, senderAvatar: null, senderType: "human",
  personaId: null, sequence: Number(id.slice(1)), createdAt: "2026-08-31T00:00:00Z",
  isSystem: false, isStreaming: false, isError: false, isStalled: false, lastActivity: 0,
});

const base = { transitions: [], loading: false, loadError: null, onRetry: () => {}, onLoadOlder: async () => 0 };

const scrollEl = (c: HTMLElement) => c.querySelector(".overflow-y-auto") as HTMLElement;
// jsdom has no layout, so fake "scrolled up" metrics on the container.
const setScrolledUp = (el: HTMLElement) => {
  Object.defineProperty(el, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: 300, configurable: true });
  Object.defineProperty(el, "scrollTop", { value: 0, writable: true, configurable: true });
};

beforeAll(() => { window.HTMLElement.prototype.scrollIntoView = vi.fn(); }); // jsdom lacks it
afterEach(cleanup);

describe("MessageList — new-messages pill", () => {
  it("appears when someone else's message arrives while scrolled up, and clears on click", async () => {
    const initial = [msg("m0"), msg("m1")];
    const { container, rerender } = render(<MessageList messages={initial} {...base} />);
    setScrolledUp(scrollEl(container));
    fireEvent.scroll(scrollEl(container)); // atBottom -> false
    rerender(<MessageList messages={[...initial, msg("m2")]} {...base} />);

    const pill = await screen.findByRole("button", { name: /new message/i }); // state is set in a deferred rAF
    expect(pill).toHaveTextContent("1 new message");
    fireEvent.click(pill);
    expect(screen.queryByRole("button", { name: /new message/i })).toBeNull();
  });

  it("does not appear for your own message", async () => {
    const initial = [msg("m0")];
    const { container, rerender } = render(<MessageList messages={initial} {...base} />);
    setScrolledUp(scrollEl(container));
    fireEvent.scroll(scrollEl(container));
    rerender(<MessageList messages={[...initial, msg("m1", "me")]} {...base} />);

    await Promise.resolve(); // let any rAF settle
    expect(screen.queryByRole("button", { name: /new message/i })).toBeNull();
  });
});

describe("MessageList — initial landing", () => {
  const origSH = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
  const origCH = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");
  beforeEach(() => {
    // jsdom has no layout — fake a scrollable container.
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 300 });
  });
  afterEach(() => {
    if (origSH) Object.defineProperty(HTMLElement.prototype, "scrollHeight", origSH);
    if (origCH) Object.defineProperty(HTMLElement.prototype, "clientHeight", origCH);
    vi.useRealTimers();
    cleanup();
  });

  // Regression: the delayed loader holds the skeleton past when messages arrive,
  // so the scroll container mounts LATER than the message-count change. The
  // initial scroll must fire on that mount — otherwise it lands at the top.
  it("lands at the bottom when the container mounts after the delayed skeleton", () => {
    vi.useFakeTimers();
    const msgs = [msg("m0"), msg("m1"), msg("m2")];
    const { container, rerender } = render(<MessageList {...base} messages={[]} loading />);
    act(() => { vi.advanceTimersByTime(200); }); // delayed skeleton appears
    expect(container.querySelector(".overflow-y-auto")).toBeNull(); // no scroll container yet

    // Messages arrive, but the loader still holds the skeleton for its min duration.
    rerender(<MessageList {...base} messages={msgs} loading={false} />);
    act(() => { vi.advanceTimersByTime(500); }); // hold releases → container mounts

    const el = container.querySelector(".overflow-y-auto") as HTMLElement;
    expect(el).not.toBeNull();
    expect(el.scrollTop).toBeGreaterThan(0); // scrolled to the latest, not stuck at the top
  });
});

describe("MessageList — a load that drags on says so", () => {
  it("after ten seconds offers Retry, which asks the chat to reload; gone once the history lands", () => {
    vi.useFakeTimers();
    try {
      const onRetry = vi.fn();
      const { rerender } = render(<MessageList messages={[]} {...base} loading onRetry={onRetry} />);
      act(() => { vi.advanceTimersByTime(9_900); });
      expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(200); });
      expect(screen.getByText(/still loading/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(onRetry).toHaveBeenCalledTimes(1);
      rerender(<MessageList messages={[msg("m1")]} {...base} loading={false} onRetry={onRetry} />);
      act(() => { vi.advanceTimersByTime(400); });
      expect(screen.queryByText(/still loading/i)).not.toBeInTheDocument();
      expect(screen.getByText("m1")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
