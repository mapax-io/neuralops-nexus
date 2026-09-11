import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelectionStore } from "@/stores/selection.store";
import { usePermissions } from "./use-permissions";
import { usePermissionsSync } from "./use-permissions-sync";

const BASE = "http://server.test:8096";

let keyedProjects: string[] = [];
let listedProjects: { id: string; name: string }[] = [];
let permissionsCalls = 0;

function payload() {
  return {
    company: { id: "c1", rights: ["project.list"] },
    projects: Object.fromEntries(keyedProjects.map((id) => [id, ["project.view", "topic.create"]])),
    topics: {},
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const render = () => {
  const { qc, wrapper } = makeWrapper();
  return { qc, ...renderHook(() => { usePermissionsSync(); return usePermissions(); }, { wrapper }) };
};

beforeEach(() => {
  permissionsCalls = 0;
  keyedProjects = ["p1"];
  listedProjects = [{ id: "p1", name: "One" }];
  useSelectionStore.setState({ byServer: {} });
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/me/permissions/`, () => { permissionsCalls += 1; return HttpResponse.json(payload()); }),
    http.get(`${BASE}/api/v1/projects/`, () =>
      HttpResponse.json(listedProjects.map((p) => ({ ...p, slug: p.id, description: null, channels: [] })))),
  );
});

// The invariant: the server keys exactly what row_rules makes visible, which is
// the same source the project list comes from. A project the app can see but
// the payload does not key is therefore stale, not a denial.
describe("usePermissionsSync", () => {
  it("does nothing while the payload and the project list agree", async () => {
    const { result } = render();
    await waitFor(() => expect(result.current.ready).toBe(true));
    await waitFor(() => expect(result.current.can("topic.create", { kind: "project", id: "p1" })).toBe(true));
    expect(permissionsCalls).toBe(1);
  });

  it("refetches when the app knows a project the payload does not key", async () => {
    const { result, qc } = render();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(permissionsCalls).toBe(1);

    // A teammate created it, or we were added to it. The project list learns
    // first (focus refetch, poll, or an explicit invalidation); the rights
    // payload is then provably behind, which is what the sync detects.
    keyedProjects = ["p1", "p2"];
    listedProjects = [...listedProjects, { id: "p2", name: "Two" }];
    await qc.invalidateQueries({ queryKey: ["projects"] });

    await waitFor(() =>
      expect(result.current.can("topic.create", { kind: "project", id: "p2" })).toBe(true),
    );
    expect(permissionsCalls).toBeGreaterThan(1);
  });

  // The dangerous case: a project that is genuinely visible with no rights on
  // it. Refetching cannot fix that, so it must ask once and stop.
  it("asks only once for a project that legitimately has no rights", async () => {
    listedProjects = [{ id: "p1", name: "One" }, { id: "p-none", name: "No rights" }];
    const { result } = render();
    await waitFor(() => expect(result.current.ready).toBe(true));
    await waitFor(() => expect(permissionsCalls).toBeGreaterThan(1));

    const settled = permissionsCalls;
    // Give it room to loop if it were going to.
    await new Promise((r) => setTimeout(r, 300));
    expect(permissionsCalls).toBe(settled);
    expect(result.current.can("topic.create", { kind: "project", id: "p-none" })).toBe(false);
  });
});
