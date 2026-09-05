import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useConnectionStore } from "@/stores/connection.store";
import { TopBar } from "./top-bar";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/w",
}));

const BASE = "http://server.test:8096";
// A real-world long name — the exact case that used to truncate to "…".
const LONG_NAME = "Noamanfaisalbinbadar's Workspace";

function renderBar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TopBar onAbout={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "member", isOwner: false, companyName: LONG_NAME, serverVersion: "dev", moduleVersions: {} },
  });
});

describe("TopBar", () => {
  it("shows the workspace name right after the app mark, capped at 50ch", () => {
    renderBar();
    const name = screen.getByText(LONG_NAME);
    // The render cap: names up to 50 characters display in full (this
    // 32-char real-world case used to ellipsize); only beyond the cap —
    // or under real space pressure — may the text clip, never the layout.
    expect(name.className).toMatch(/max-w-\[50ch\]/);
    // After the logo means INSIDE the home button, next to the mark.
    expect(screen.getByRole("button", { name: LONG_NAME })).toContainElement(name);
  });

  it("falls back to a generic label without a connection", () => {
    useConnectionStore.setState({ connection: null });
    renderBar();
    expect(screen.getByRole("button", { name: "Workspace" })).toBeInTheDocument();
  });
});

