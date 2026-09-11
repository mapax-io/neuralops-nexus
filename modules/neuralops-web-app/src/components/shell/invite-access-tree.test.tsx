import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { Selection } from "@/lib/invite-grants";
import { InviteAccessTree } from "./invite-access-tree";

const BASE = "http://server.test:8096";
const PROJECTS = [
  {
    id: "p1", name: "Alpha", slug: "alpha", description: null,
    channels: [
      { id: "c1", name: "general", slug: "general", description: null },
      { id: "c2", name: "design", slug: "design", description: null },
      { id: "c3", name: "empty", slug: "empty", description: null },
    ],
  },
  { id: "p2", name: "Beta", slug: "beta", description: null, channels: [] },
];
const topic = (id: string, title: string, cid: string) => ({ id, title, slug: title, channel_id: cid, project_id: "p1" });

let latest: Selection = {};
// Outside the component on purpose: a component must not write module state.
const record = (next: Selection) => { latest = next; };

function Harness({ initial = {} }: { initial?: Selection }) {
  const [sel, setSel] = useState<Selection>(initial);
  const onChange = (next: Selection) => {
    record(next);
    setSel(next);
  };
  return <InviteAccessTree selection={sel} onChange={onChange} idPrefix="t" />;
}

function renderTree(initial?: Selection) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Harness initial={initial} />
    </QueryClientProvider>,
  );
}

const box = (name: string | RegExp) => screen.getByRole("checkbox", { name });
const expand = async (name: string) => fireEvent.click(await screen.findByRole("button", { name, expanded: false }));

beforeEach(() => {
  latest = {};
  useConnectionStore.setState({ serverUrl: BASE, token: "jwt" });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => HttpResponse.json([topic("t1", "chat#1", "c1"), topic("t2", "chat#2", "c1")])),
    http.get(`${BASE}/api/v1/projects/p1/channels/c2/topics/`, () => HttpResponse.json([topic("t3", "chat#3", "c2")])),
    http.get(`${BASE}/api/v1/projects/p1/channels/c3/topics/`, () => HttpResponse.json([])),
  );
});

describe("InviteAccessTree — states", () => {
  // The loader is delayed (a cached list never shows one) and held once shown.
  it("holds a loader while projects load, then lists them unchecked and collapsed", async () => {
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => { release = r; });
    server.use(http.get(`${BASE}/api/v1/projects/`, async () => { await gate; return HttpResponse.json(PROJECTS); }));
    renderTree();
    expect(screen.queryByRole("status")).not.toBeInTheDocument(); // not yet — no flash for fast loads
    expect(await screen.findByRole("status", { name: /loading projects/i })).toBeInTheDocument();
    release!();
    expect(await screen.findByRole("checkbox", { name: "Add to Alpha" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("button", { name: "Alpha" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("checkbox", { name: /chat#1/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("No project picked");
  });

  it("reports a projects failure with a retry", async () => {
    let fail = true;
    server.use(http.get(`${BASE}/api/v1/projects/`, () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(PROJECTS))));
    renderTree();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load projects.");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("checkbox", { name: "Add to Alpha" })).toBeInTheDocument();
  });

  it("says so when the server has no projects", async () => {
    server.use(http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([])));
    renderTree();
    expect(await screen.findByText(/no projects on this server yet/i)).toBeInTheDocument();
  });

  it("fetches a project's topics only when it is opened, holding a line while they load", async () => {
    let hits = 0;
    let release: (() => void) | null = null;
    const gate = new Promise<void>((r) => { release = r; });
    server.use(http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, async () => {
      hits += 1;
      await gate;
      return HttpResponse.json([topic("t1", "chat#1", "c1"), topic("t2", "chat#2", "c1")]);
    }));
    renderTree();
    await screen.findByRole("checkbox", { name: "Add to Alpha" });
    expect(hits).toBe(0);
    await expand("Alpha");
    expect(await screen.findByText("Loading topics…")).toBeInTheDocument();
    release!();
    expect(await screen.findByRole("checkbox", { name: "Add to chat#1" })).toBeInTheDocument();
    expect(hits).toBe(1);
  });

  it("shows channels with their topics; a channel with none is disabled and says so", async () => {
    renderTree();
    await expand("Alpha");
    await screen.findByRole("checkbox", { name: "Add to chat#1" });
    expect(box("Add to every topic in #general")).toBeEnabled();
    expect(box("Add to every topic in #empty")).toBeDisabled();
    expect(screen.getByText("no topics yet")).toBeInTheDocument();
  });

  it("a project without channels says the whole project is the only option", async () => {
    renderTree();
    await expand("Beta");
    expect(await screen.findByText(/whole project is the only option/i)).toBeInTheDocument();
  });

  it("reports a topics failure with a retry", async () => {
    let fail = true;
    server.use(http.get(`${BASE}/api/v1/projects/p1/channels/c2/topics/`, () =>
      fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json([topic("t3", "chat#3", "c2")])));
    renderTree();
    await expand("Alpha");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load topics.");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: /retry/i }));
    expect(await screen.findByRole("checkbox", { name: "Add to chat#3" })).toBeInTheDocument();
  });
});

describe("InviteAccessTree — picking", () => {
  it("ticking a project is the whole project: it opens, every box below is on, and it is summarized", async () => {
    renderTree();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to Alpha" }));
    expect(box("Add to Alpha")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("button", { name: /^Alpha/ })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("checkbox", { name: "Add to chat#3" })).toHaveAttribute("aria-checked", "true");
    expect(box("Add to every topic in #general")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("whole project")).toBeInTheDocument();
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("Alpha (whole project)");
    expect(latest).toEqual({ p1: "all" });
  });

  it("unticking one topic narrows the project and marks it and its channel as mixed", async () => {
    renderTree();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to Alpha" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to chat#2" }));
    expect(box("Add to Alpha")).toHaveAttribute("aria-checked", "mixed");
    expect(box("Add to every topic in #general")).toHaveAttribute("aria-checked", "mixed");
    expect(box("Add to every topic in #design")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByText("whole project")).not.toBeInTheDocument();
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("Alpha (2 of 3 topics)");
    expect(latest).toEqual({ p1: ["t1", "t3"] });
  });

  it("a channel box moves all of its topics at once", async () => {
    renderTree();
    await expand("Alpha");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to every topic in #general" }));
    expect(box("Add to chat#1")).toHaveAttribute("aria-checked", "true");
    expect(box("Add to chat#2")).toHaveAttribute("aria-checked", "true");
    expect(box("Add to chat#3")).toHaveAttribute("aria-checked", "false");
    expect(latest).toEqual({ p1: ["t1", "t2"] });
    fireEvent.click(box("Add to every topic in #general"));
    expect(latest).toEqual({});
  });

  it("ticking every topic by hand becomes the whole project", async () => {
    renderTree();
    await expand("Alpha");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to chat#1" }));
    fireEvent.click(box("Add to chat#2"));
    fireEvent.click(box("Add to chat#3"));
    expect(box("Add to Alpha")).toHaveAttribute("aria-checked", "true");
    expect(latest).toEqual({ p1: "all" });
  });

  it("collapsing a project keeps what was picked", async () => {
    renderTree();
    await expand("Alpha");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to chat#3" }));
    fireEvent.click(screen.getByRole("button", { name: /^Alpha/ }));
    expect(screen.queryByRole("checkbox", { name: "Add to chat#3" })).not.toBeInTheDocument();
    expect(box("Add to Alpha")).toHaveAttribute("aria-checked", "mixed");
    fireEvent.click(screen.getByRole("button", { name: /^Alpha/ }));
    expect(await screen.findByRole("checkbox", { name: "Add to chat#3" })).toHaveAttribute("aria-checked", "true");
  });

  it("projects are independent", async () => {
    renderTree();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to Beta" }));
    await expand("Alpha");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Add to chat#1" }));
    expect(latest).toEqual({ p2: "all", p1: ["t1"] });
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("Beta (whole project) · Alpha (1 of 3 topics)");
    fireEvent.click(box("Add to Beta"));
    expect(latest).toEqual({ p1: ["t1"] });
  });
});
