import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { MCPServer } from "@/lib/api/intelligence";
import { McpTab } from "./mcp-tab";

const BASE = "http://server.test:8096";
const SERVERS_URL = `${BASE}/api/v1/mcp-servers/`;
const PROJECTS_URL = `${BASE}/api/v1/projects/`;

// MCP servers belong to exactly ONE project (FK, non-transferable) — the
// per-project scoping below is the contract these tests pin.
const S1: MCPServer = {
  id: "s1",
  name: "Warehouse tools",
  description: "SQL over the sales warehouse",
  project_id: "p1",
  server_type: "remote",
  transport: "http",
  url: "http://tools.internal:8080/mcp",
  timeout_seconds: 60,
  embed_output: false,
  auth_type: "none",
  oauth_config: null,
  oauth_connected: false,
};

const PROJECTS = [
  { id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] },
  { id: "p2", name: "Zephyr", slug: "zephyr", description: null, channels: [] },
];

let posted: Record<string, unknown> | null = null;

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <McpTab />
    </QueryClientProvider>,
  );
}

async function openCreateDialog() {
  fireEvent.click(await screen.findByRole("button", { name: /add server/i }));
  await screen.findByLabelText("Project");
}

function fillCreate({ projectId, name, url }: { projectId?: string; name: string; url: string }) {
  if (projectId) fireEvent.change(screen.getByLabelText("Project"), { target: { value: projectId } });
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("URL"), { target: { value: url } });
}

const submitCreate = () => fireEvent.submit(document.getElementById("mcp-form")!);

beforeEach(() => {
  posted = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(SERVERS_URL, () => HttpResponse.json([S1])),
    http.get(PROJECTS_URL, () => HttpResponse.json(PROJECTS)),
    http.post(SERVERS_URL, async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...S1, id: "s2", ...posted });
    }),
  );
});

describe("McpTab — single-project ownership (spec §3.3)", () => {
  it("shows each server under its one owning project", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    expect(screen.getByText("Apollo")).toBeInTheDocument();
    expect(screen.queryByText("Zephyr")).not.toBeInTheDocument();
  });

  it("refuses to create a server without a project", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fillCreate({ name: "New tools", url: "http://new.internal/mcp" });
    submitCreate();
    await screen.findByText("Pick the project this server belongs to.");
    expect(posted).toBeNull();
  });

  it("blocks a duplicate name within the same project", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fillCreate({ projectId: "p1", name: "Warehouse tools", url: "http://other.internal/mcp" });
    submitCreate();
    await screen.findByText("This project already has an MCP server with this name.");
    expect(posted).toBeNull();
  });

  it("blocks a duplicate connection within the same project even under a new name", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fillCreate({ projectId: "p1", name: "Same endpoint again", url: S1.url! });
    submitCreate();
    await screen.findByText(/exact connection details/);
    expect(posted).toBeNull();
  });

  it("allows the same name and connection in a DIFFERENT project and posts its project_id", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fillCreate({ projectId: "p2", name: "Warehouse tools", url: S1.url! });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ project_id: "p2", name: "Warehouse tools", auth_type: "none" });
  });

  it("offers no project control when editing — ownership is not transferable", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Warehouse tools" }));
    await screen.findByText("Edit Warehouse tools");
    expect(screen.getByLabelText("Name")).toHaveValue("Warehouse tools");
    expect(screen.queryByLabelText("Project")).not.toBeInTheDocument();
  });
});
