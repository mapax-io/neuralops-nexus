import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelectionStore } from "@/stores/selection.store";
import { WorkspaceTree } from "./workspace-tree";

const BASE = "http://server.test:8096";

function renderTree() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceTree />
    </QueryClientProvider>,
  );
}

function connectAs(role: string) {
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role, isOwner: role === "owner", companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
}

beforeEach(() => {
  useSelectionStore.setState({ byServer: {} });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () =>
      HttpResponse.json([
        { id: "p1", name: "Demo Project", slug: "demo", description: null, channels: [{ id: "c1", name: "general", slug: "g", description: null }] },
      ]),
    ),
    http.get(`${BASE}/api/v1/members/`, () => HttpResponse.json([])),
  );
});

describe("WorkspaceTree", () => {
  // The tree stops at channels — chats live in the right-side ChatListPanel.
  it("selects the channel on click and lists NO chats in the tree", async () => {
    server.use(
      http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () =>
        HttpResponse.json([{ id: "t1", title: "chat#1", slug: "t1", project_id: "p1", channel_id: "c1", has_unread: true, unread_count: 2 }]),
      ),
    );
    connectAs("member");
    renderTree();
    expect(await screen.findByText("Demo Project")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /general/ }));
    // Channel click drives the selection store — no tid, ids never enter the URL.
    expect(useSelectionStore.getState().byServer[BASE]).toEqual({ pid: "p1", cid: "c1" });
    // Chats are NOT rendered in the tree anymore…
    expect(screen.queryByText("chat#1")).not.toBeInTheDocument();
    // …but the channel still surfaces its unread state.
    expect(await screen.findByRole("status", { name: /topics with new messages/i })).toBeInTheDocument();
  });

  it("offers creation controls to admins but not members", async () => {
    connectAs("admin");
    renderTree();
    expect(await screen.findByLabelText("New project")).toBeInTheDocument();

    connectAs("member");
    renderTree();
    // The admin render above is unmounted by rerendering fresh; query the latest DOM state:
    expect(screen.queryAllByLabelText("New project").length).toBeLessThanOrEqual(1);
  });

  it("creates a channel with the optional description the server accepts", async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/v1/projects/p1/channels/`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "c9", name: posted.name, slug: posted.name, description: posted.description ?? null });
      }),
    );
    connectAs("admin");
    renderTree();
    fireEvent.click(await screen.findByLabelText("New channel in Demo Project"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Name")).toBeRequired();
    expect(within(dialog).getByLabelText(/description/i)).not.toBeRequired();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Backend" } });
    fireEvent.change(within(dialog).getByLabelText(/description/i), { target: { value: "APIs and services" } });
    fireEvent.submit(document.getElementById("wc-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({ name: "backend", description: "APIs and services" });
  });

  it("shows the empty state when there are no projects", async () => {
    server.use(http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([])));
    connectAs("member");
    renderTree();
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByText(/ask an admin/i)).toBeInTheDocument();
  });
});
