import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "./msw/server";

// findBy*/waitFor default to 1s, which is marginal for this suite: the heavier
// component files render real trees and drive a dozen msw round trips each,
// and vitest runs files across 11 workers, so a machine under load pushes some
// of them past the second. That showed up as a handful of DIFFERENT tests
// failing on different runs -- every one of them passing in isolation.
//
// This is not a way to hide slow code: a genuinely broken assertion still
// fails, just later. It removes CPU contention as a cause of failure so a red
// run means something.
configure({ asyncUtilTimeout: 5_000 });

// jsdom gaps the app relies on.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  }));
}
if (!("IntersectionObserver" in window)) {
  class IO {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  Object.assign(window, { IntersectionObserver: IO });
}

// Unhandled requests fail the test: every network call must be an explicit handler.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
