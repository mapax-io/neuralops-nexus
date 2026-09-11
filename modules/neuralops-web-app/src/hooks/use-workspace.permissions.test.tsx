import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { projectScope, topicScope } from "@/lib/permissions";
import { usePermissions } from "./use-permissions";
import { useCreateProject, useCreateTopic } from "./use-workspace";

const BASE = "http://server.test:8096";

// The rights payload is keyed by object id, so an object that did not exist
// when it was fetched is absent from it -- and every control scoped to that
// object reads as denied. This is what made a brand-new project show no
// "Start the first topic" button until the page was refreshed.
let knownProjects: string[] = [];
let knownTopics: string[] = [];

function permissionsPayload() {
  const all = ["project.view", "topic.create", "topic.list", "channel.list"];
  return {
    company: { id: "c1", rights: ["project.list", "project.create"] },
    projects: Object.fromEntries(knownProjects.map((id) => [id, all])),
    topics: Object.fromEntries(knownTopics.map((id) => [id, ["topic.update", "persona.mention"]])),
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  knownProjects = ["p1"];
  knownTopics = [];
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/me/permissions/`, () => HttpResponse.json(permissionsPayload())),
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([])),
    http.post(`${BASE}/api/v1/projects/`, async ({ request }) => {
      const body = (await request.json()) as { name: string };
      // The server grants the creator rights on it; the payload only reflects
      // that on the next fetch.
      knownProjects = [...knownProjects, "p-new"];
      return HttpResponse.json({ id: "p-new", name: body.name, slug: "new", description: null, channels: [] });
    }),
    http.get(`${BASE}/api/v1/projects/:pid/channels/:cid/topics/`, () => HttpResponse.json([])),
    http.post(`${BASE}/api/v1/projects/:pid/channels/:cid/topics/`, () => {
      knownTopics = [...knownTopics, "t-new"];
      return HttpResponse.json({ id: "t-new", title: "Topic 1", slug: "t1", project_id: "p1", channel_id: "c1" });
    }),
  );
});

describe("creating an object refreshes the rights that govern it", () => {
  it("a newly created project can be acted on without a page refresh", async () => {
    const { result } = renderHook(
      () => ({ perms: usePermissions(), create: useCreateProject() }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.perms.ready).toBe(true));
    // Before: the new project does not exist, so nothing is permitted on it.
    expect(result.current.perms.can("topic.create", projectScope("p-new"))).toBe(false);

    result.current.create.mutate({ name: "New Project" });

    // After the mutation settles the control must be live — no refresh.
    await waitFor(() =>
      expect(result.current.perms.can("topic.create", projectScope("p-new"))).toBe(true),
    );
  });

  it("a newly created topic can be acted on without a page refresh", async () => {
    const { result } = renderHook(
      () => ({ perms: usePermissions(), create: useCreateTopic("p1", "c1") }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.perms.ready).toBe(true));
    expect(result.current.perms.can("topic.update", topicScope("t-new"))).toBe(false);

    result.current.create.mutate([]);

    await waitFor(() =>
      expect(result.current.perms.can("topic.update", topicScope("t-new"))).toBe(true),
    );
  });

  // Ordering, not just eventual consistency: onDone runs AFTER the refetch, so
  // whatever it navigates to already has answerable rights. Read from the cache
  // rather than a hook snapshot, which would be the closure from an earlier
  // render and prove nothing.
  it("refreshes the rights before handing the new project to the caller", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const withClient = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    let rightsAtCallback: string[] | undefined;
    const { result } = renderHook(
      () => ({
        perms: usePermissions(),
        create: useCreateProject(() => {
          const cached = qc.getQueryData<{ projects: Record<string, string[]> }>(["permissions", BASE]);
          rightsAtCallback = cached?.projects["p-new"];
        }),
      }),
      { wrapper: withClient },
    );
    await waitFor(() => expect(result.current.perms.ready).toBe(true));

    result.current.create.mutate({ name: "New Project" });

    await waitFor(() => expect(rightsAtCallback).toBeDefined());
    expect(rightsAtCallback).toContain("topic.create");
  });
});
