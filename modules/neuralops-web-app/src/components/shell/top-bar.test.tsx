import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useConnectionStore } from "@/stores/connection.store";
import { useUiStore } from "@/stores/ui.store";
import { TopBar } from "./top-bar";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
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
  push.mockClear();
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

describe("TopBar — mobile navigation menu", () => {
  const openMenu = () => {
    fireEvent.click(screen.getByRole("button", { name: "Navigation menu" }));
    return screen.getByRole("menu", { name: "Navigation" });
  };

  it("lists every nav destination plus About under the hamburger", () => {
    renderBar();
    openMenu();
    for (const label of ["Personas", "AI models", "MCP servers", "Members", "About NeuralOps Nexus"]) {
      expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
    }
  });

  it("offers no Agents destination anywhere — agents collapsed into personas", () => {
    renderBar();
    expect(screen.queryByRole("button", { name: "Agents" })).not.toBeInTheDocument();
    openMenu();
    expect(screen.queryByRole("menuitem", { name: "Agents" })).not.toBeInTheDocument();
  });

  it("navigates to the picked intelligence section and closes", () => {
    renderBar();
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "MCP servers" }));
    expect(useUiStore.getState().intelSection).toBe("mcp");
    expect(push).toHaveBeenCalledWith("/intelligence");
    expect(screen.queryByRole("menu", { name: "Navigation" })).not.toBeInTheDocument();
  });

  it("fires the About dialog from the menu", () => {
    const onAbout = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <TopBar onAbout={onAbout} />
      </QueryClientProvider>,
    );
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "About NeuralOps Nexus" }));
    expect(onAbout).toHaveBeenCalled();
  });

  it("closes on Escape and returns focus to the hamburger", () => {
    renderBar();
    openMenu();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu", { name: "Navigation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Navigation menu" })).toHaveFocus();
  });
});
