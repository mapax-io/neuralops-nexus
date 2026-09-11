import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { grantAll } from "@/test/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import WorkspaceLayout from "./layout";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/w",
}));

const BASE = "http://server.test:8096";

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceLayout>
        <div>workspace content</div>
      </WorkspaceLayout>
    </QueryClientProvider>,
  );
}

// Rendering the REAL layout mounts the whole shell (top bar, tree, banners),
// which fetches on its own. These keep msw's strict unhandled-request mode from
// failing the test for calls this file is not about.
function shellHandlers() {
  server.use(
    http.get(`${BASE}/api/v1/auth/verify/`, () => HttpResponse.json({
      ok: true, email: "o@acme.test", user_id: "u1", is_new_user: false,
      company_exists: true, is_owner: true, role: "owner", company_name: "Acme",
      server_version: "dev",
    })),
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/members/`, () => HttpResponse.json([])),
  );
}

const connected = () =>
  useConnectionStore.setState({
    hydrated: true,
    token: "jwt",
    serverUrl: BASE,
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });

beforeEach(() => {
  useConnectionStore.setState({ hydrated: false, token: null, serverUrl: null, connection: null });
});

describe("WorkspaceLayout — before the session is known", () => {
  it("shows the full-page loader with the app mark, never a bare skeleton box", () => {
    const { container } = renderLayout();
    const status = screen.getByRole("status", { name: /loading/i });
    expect(status).toBeInTheDocument();
    expect(status.querySelector("svg")).not.toBeNull(); // the mark, not an empty rectangle
    expect(container.querySelector(".nx-shimmer")).toBeNull();
    expect(screen.queryByText("workspace content")).not.toBeInTheDocument();
  });
});

// The live regression: signed in as owner, the shell rendered before rights
// arrived, so every gated control resolved to hidden and "New topic" was
// missing until a refresh. The shell must hold, not paint a half-answer.
describe("WorkspaceLayout — before rights are known", () => {
  it("holds the loader while permissions are still in flight", async () => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => { release = r; });
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, async () => {
      await gate;
      return HttpResponse.json({ company: { id: "c1", rights: [] }, projects: {}, topics: {} });
    }));
    shellHandlers();
    connected();
    renderLayout();

    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.queryByText("workspace content")).not.toBeInTheDocument();

    release!();
    await waitFor(() => expect(screen.getByText("workspace content")).toBeInTheDocument());
  });

  it("renders once rights have arrived", async () => {
    server.use(grantAll(BASE, { projects: ["p1"], topics: [] }));
    shellHandlers();
    connected();
    renderLayout();
    await waitFor(() => expect(screen.getByText("workspace content")).toBeInTheDocument());
  });

  // Holding forever would be worse than the bug: a server without the endpoint
  // must still render, with PermissionsBanner explaining the missing controls.
  it("does not hold the app against a server that has no permissions route", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 404 })));
    shellHandlers();
    connected();
    renderLayout();
    await waitFor(() => expect(screen.getByText("workspace content")).toBeInTheDocument(), { timeout: 6000 });
  }, 12_000);
});
