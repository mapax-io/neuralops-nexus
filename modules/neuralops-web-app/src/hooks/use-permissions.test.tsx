import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { companyScope, projectScope, topicScope, type Permissions } from "@/lib/permissions";
import { usePermissions } from "./use-permissions";

const BASE = "http://server.test:8096";

const PAYLOAD: Permissions = {
  company: { id: "c1", rights: ["project.list", "company.invite_member"] },
  projects: { p1: ["project.view", "persona.create"] },
  topics: { t1: ["persona.mention"] },
};

// The role is set only because the store's connection object carries it, and
// is varied on purpose below to prove the hook never consults it.
function connect(role: string | null) {
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role, isOwner: role === "owner", companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const renderGate = () => renderHook(() => usePermissions(), { wrapper });

beforeEach(() => {
  useConnectionStore.setState({ serverUrl: null, token: null, connection: null });
});

describe("answers from the server payload", () => {
  beforeEach(() => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => HttpResponse.json(PAYLOAD)));
  });

  it("reports ready and resolves each scope from its own key", async () => {
    connect("member");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.can("company.invite_member", companyScope())).toBe(true);
    expect(result.current.can("persona.create", projectScope("p1"))).toBe(true);
    expect(result.current.can("persona.create", projectScope("p2"))).toBe(false);
    expect(result.current.can("persona.mention", topicScope("t1"))).toBe(true);
  });

  // The bug this change exists to fix: a project admin whose CompanyAccess.role
  // is 'member' must get the controls for their own project.
  it("gives a project admin their controls despite a member company role", async () => {
    connect("member");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.can("persona.create", projectScope("p1"))).toBe(true);
  });

  // The other direction: a company 'admin' who does not hold the right stops
  // seeing the button instead of collecting a 403.
  it("hides a control from a company admin who does not hold the right", async () => {
    connect("admin");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.can("persona.create", projectScope("p2"))).toBe(false);
  });

  it("gives an owner nothing the payload does not list", async () => {
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.can("company.remove_member", companyScope())).toBe(false);
  });

  it("answers canAnyProject across the payload's project keys", async () => {
    connect("member");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.canAnyProject("persona.create")).toBe(true);
    expect(result.current.canAnyProject("model_config.attach")).toBe(false);
  });
});

// A server that predates the endpoint. The client holds no rule of its own to
// fall back on — role bundles are editable server-side and could never express
// a project-scoped assignment — so it reports the server as out of date and
// offers nothing. PermissionsBanner is what makes that visible.
describe("endpoint absent (404)", () => {
  beforeEach(() => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 404 })));
  });

  it("reports the server as too old", async () => {
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.serverTooOld).toBe(true));
    expect(result.current.ready).toBe(false);
  });

  it("offers nothing, whatever the company role says", async () => {
    for (const role of ["owner", "admin", "member", "viewer"]) {
      connect(role);
      const { result } = renderGate();
      await waitFor(() => expect(result.current.serverTooOld).toBe(true));
      expect(result.current.can("persona.create", projectScope("p1"))).toBe(false);
      expect(result.current.can("company.invite_member", companyScope())).toBe(false);
      expect(result.current.can("topic.mark_read", topicScope("t1"))).toBe(false);
      expect(result.current.canAnyProject("model_config.attach")).toBe(false);
    }
  });
});

// A failed fetch must not be mistaken for a loaded answer — it stays "not
// ready" so a later refetch can still resolve it.
describe("transient failure", () => {
  it("is not mistaken for an out-of-date server", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 500 })));
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(false));
    // A 500 is transient: it must not claim the server lacks the route, or the
    // banner would blame the wrong thing and the query would stop retrying.
    expect(result.current.serverTooOld).toBe(false);
    expect(result.current.can("persona.create", projectScope("p1"))).toBe(false);
  });
});

// The live regression: an owner signed in, the shell rendered before the
// rights arrived, and every gated control resolved to hidden -- so "New topic"
// was missing until a refresh. `loading` is what lets a screen hold instead of
// painting an answer it does not have yet.
describe("loading is distinguishable from holding nothing", () => {
  it("reports loading while the request is in flight, and not after", async () => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => { release = r; });
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, async () => {
      await gate;
      return HttpResponse.json(PAYLOAD);
    }));
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.loading).toBe(true));
    // Mid-flight the answer is genuinely unknown -- not "you hold nothing".
    expect(result.current.ready).toBe(false);
    expect(result.current.can("persona.create", projectScope("p1"))).toBe(false);
    release!();
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.loading).toBe(false);
  });

  it("stops loading once the server answers 404, so the screen is not held forever", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 404 })));
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.serverTooOld).toBe(true));
    expect(result.current.loading).toBe(false);
    // An absent route is not a failure to retry -- different banner, no retry.
    expect(result.current.failed).toBe(false);
  });

  // A 500 is retried (the hook's own retry policy overrides the test client's),
  // so loading stays true across attempts -- correct, the answer really is
  // still unknown -- and only clears once the attempts are exhausted.
  it("stops loading once a transient failure has exhausted its retries, and reports it", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 500 })));
    connect("owner");
    const { result } = renderGate();
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10_000 });
    expect(result.current.ready).toBe(false);
    // Not an out-of-date server -- a failure, which is separately reportable
    // and retryable. Without this the app hides every control and says nothing.
    expect(result.current.serverTooOld).toBe(false);
    expect(result.current.failed).toBe(true);
  }, 15_000);

  it("is not loading before a server is connected — a disabled query must not hold the app", async () => {
    const { result } = renderGate();
    await waitFor(() => expect(result.current.loading).toBe(false));
  });
});

describe("before the connection exists", () => {
  it("does not fire the query, and does not blame the server", async () => {
    // enabled:false plus apiJson's own "No server connected." guard — nothing
    // is fetched and nothing is offered.
    const { result } = renderGate();
    await waitFor(() => expect(result.current.ready).toBe(false));
    expect(result.current.serverTooOld).toBe(false);
    expect(result.current.can("project.create", companyScope())).toBe(false);
  });
});
