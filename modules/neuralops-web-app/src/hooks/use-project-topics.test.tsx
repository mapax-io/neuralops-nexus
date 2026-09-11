import { beforeEach, describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { useProjectTopics, useProjectsTopics } from "./use-workspace";

const BASE = "http://server.test:8096";
const PROJECTS = [
  {
    id: "p1", name: "Alpha", slug: "alpha", description: null,
    channels: [
      { id: "c1", name: "general", slug: "general", description: null },
      { id: "c2", name: "design", slug: "design", description: null },
    ],
  },
  { id: "p2", name: "Beta", slug: "beta", description: null, channels: [] },
];
const topic = (id: string, cid: string) => ({ id, title: id, slug: id, channel_id: cid, project_id: "p1" });

function setup(projectId?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const hook = renderHook(({ pid }: { pid?: string }) => useProjectTopics(pid), { wrapper, initialProps: { pid: projectId } });
  return { qc, ...hook };
}

beforeEach(() => {
  useConnectionStore.setState({ serverUrl: BASE, token: "jwt" });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => HttpResponse.json([topic("t1", "c1")])),
    http.get(`${BASE}/api/v1/projects/p1/channels/c2/topics/`, () => HttpResponse.json([topic("t2", "c2"), topic("t3", "c2")])),
  );
});

describe("useProjectTopics — every topic in a project, by channel", () => {
  it("loads each channel's topics and groups them under it, in channel order", async () => {
    const { result } = setup("p1");
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups.map((g) => [g.channel.name, g.topics.map((t) => t.id)])).toEqual([
      ["general", ["t1"]],
      ["design", ["t2", "t3"]],
    ]);
    expect(result.current.error).toBeNull();
  });

  // The sidebar reads ["topics", serverUrl, pid, cid] through useTopics; one
  // cache, not a second copy that can disagree with it.
  it("shares the sidebar's cache: the same key useTopics reads", async () => {
    const { qc, result } = setup("p1");
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(qc.getQueryData(["topics", BASE, "p1", "c1"])).toEqual([topic("t1", "c1")]);
  });

  it("is empty — and fetches nothing — with no project, or a project with no channels", async () => {
    let hits = 0;
    server.use(http.get(`${BASE}/api/v1/projects/:pid/channels/:cid/topics/`, () => { hits += 1; return HttpResponse.json([]); }));
    const none = setup(undefined);
    await waitFor(() => expect(none.result.current.loading).toBe(false));
    expect(none.result.current.groups).toEqual([]);
    const bare = setup("p2");
    await waitFor(() => expect(bare.result.current.loading).toBe(false));
    expect(bare.result.current.groups).toEqual([]);
    expect(hits).toBe(0);
  });

  it("surfaces one channel's failure without hiding the others, and retry refetches only it", async () => {
    let fail = true;
    let c1Hits = 0;
    server.use(
      http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => { c1Hits += 1; return HttpResponse.json([topic("t1", "c1")]); }),
      http.get(`${BASE}/api/v1/projects/p1/channels/c2/topics/`, () =>
        fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json([topic("t2", "c2")])),
    );
    const { result } = setup("p1");
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).not.toBeNull();
    expect(result.current.groups[0].topics.map((t) => t.id)).toEqual(["t1"]);
    expect(c1Hits).toBe(1);
    fail = false;
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.groups[1].topics.map((t) => t.id)).toEqual(["t2"]);
    expect(c1Hits).toBe(1);
  });

  // The batch form the single one delegates to: several projects, one answer.
  it("lists several projects at once, keyed by project, on the same cache", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useProjectsTopics(["p1", "p2"]), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(Object.keys(result.current.byProject).sort()).toEqual(["p1", "p2"]);
    expect(result.current.byProject.p1.map((g) => g.topics.length)).toEqual([1, 2]);
    expect(result.current.byProject.p2).toEqual([]);
    expect(qc.getQueryData(["topics", BASE, "p1", "c2"])).toHaveLength(2);
  });

  it("follows the project when it changes", async () => {
    const { result, rerender } = setup("p1");
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups).toHaveLength(2);
    rerender({ pid: "p2" });
    await waitFor(() => expect(result.current.groups).toEqual([]));
  });
});
