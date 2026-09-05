import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  command: null,
  timeout_seconds: 60,
  max_retries: 3,
  config: {},
  is_first_party: false,
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

  it("marks project, name and URL as required — description stays optional", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    for (const field of ["Project", "Name", "URL"]) expect(screen.getByLabelText(field)).toBeRequired();
    expect(screen.getByLabelText(/description/i)).not.toBeRequired();
  });

  it("offers the four transports, defaults to HTTP, and swaps the URL for a command on STDIO", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    const transport = screen.getByLabelText("Transport") as HTMLSelectElement;
    expect(transport.value).toBe("http");
    expect(within(transport).getAllByRole("option").map((o) => (o as HTMLOptionElement).value)).toEqual(["http", "sse", "websocket", "stdio"]);
    expect(screen.getByLabelText("URL")).toBeInTheDocument();
    fireEvent.change(transport, { target: { value: "stdio" } });
    expect(screen.queryByLabelText("URL")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Command")).toBeRequired();
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "p2" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Local files" } });
    fireEvent.change(screen.getByLabelText("Command"), { target: { value: "npx -y @modelcontextprotocol/server-filesystem /data" } });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ project_id: "p2", transport: "stdio", server_type: "local", command: "npx -y @modelcontextprotocol/server-filesystem /data" });
    expect(posted).not.toHaveProperty("url");
  });

  it("posts the chosen remote transport with the URL", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fireEvent.change(screen.getByLabelText("Transport"), { target: { value: "sse" } });
    fillCreate({ projectId: "p2", name: "Events", url: "http://events.internal/sse" });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ transport: "sse", server_type: "remote", url: "http://events.internal/sse" });
  });

  it("shows the transport as fixed when editing and offers the command field for a STDIO server", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([{ ...S1, id: "s3", name: "Local files", transport: "stdio", server_type: "local", url: null, command: "npx -y server-fs /data" }])));
    renderTab();
    await screen.findByText("Local files");
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Local files" }));
    await screen.findByText("Edit Local files");
    expect(screen.queryByLabelText("Transport")).not.toBeInTheDocument();
    expect(screen.getByText(/stdio/i, { selector: "code" })).toBeInTheDocument();
    expect(screen.getByLabelText("Command")).toHaveValue("npx -y server-fs /data");
    expect(screen.queryByLabelText("URL")).not.toBeInTheDocument();
  });

  it("posts the call settings on create and patches only a changed one on edit", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    expect(screen.getByLabelText("Timeout (seconds)")).toHaveValue(60);
    expect(screen.getByLabelText("Max retries")).toHaveValue(3);
    fireEvent.change(screen.getByLabelText("Timeout (seconds)"), { target: { value: "120" } });
    fillCreate({ projectId: "p2", name: "Slow tools", url: "http://slow.internal/mcp" });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ timeout_seconds: 120, max_retries: 3 });
    fireEvent.keyDown(document, { key: "Escape" });

    let patched: Record<string, unknown> | null = null;
    server.use(http.patch(`${SERVERS_URL}:id/`, async ({ request }) => { patched = (await request.json()) as Record<string, unknown>; return HttpResponse.json({ ...S1, ...patched }); }));
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Warehouse tools" }));
    await screen.findByText("Edit Warehouse tools");
    fireEvent.change(screen.getByLabelText("Max retries"), { target: { value: "5" } });
    fireEvent.submit(document.getElementById("mce-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ max_retries: 5 });
  });

  it("carries the runtime fields the worker reads: config JSON, first-party and embed flags", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    const embed = screen.getByLabelText(/embed tool output/i) as HTMLInputElement;
    expect(embed).toBeDisabled(); // only meaningful for a first-party server
    fireEvent.click(screen.getByLabelText(/first-party server/i));
    expect(embed).toBeEnabled();
    fireEvent.click(embed);
    fireEvent.change(screen.getByLabelText(/extra configuration/i), { target: { value: "{ not json" } });
    fillCreate({ projectId: "p2", name: "Files", url: "http://files.internal/mcp" });
    submitCreate();
    await screen.findByText(/must be a JSON object/i);
    expect(posted).toBeNull();
    fireEvent.change(screen.getByLabelText(/extra configuration/i), { target: { value: '{"root_path": "/data"}' } });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ config: { root_path: "/data" }, is_first_party: true, embed_output: true });
  });

  it("edits config and the embed flag; first-party stays fixed as the server's PATCH lacks it", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([{ ...S1, is_first_party: true, embed_output: false, config: { root_path: "/old" } }])));
    let patched: Record<string, unknown> | null = null;
    server.use(http.patch(`${SERVERS_URL}:id/`, async ({ request }) => { patched = (await request.json()) as Record<string, unknown>; return HttpResponse.json({ ...S1, ...patched }); }));
    renderTab();
    await screen.findByText("Warehouse tools");
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Warehouse tools" }));
    await screen.findByText("Edit Warehouse tools");
    expect(screen.queryByLabelText(/first-party server/i)).not.toBeInTheDocument();
    expect(screen.getByText(/first-party/i, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByLabelText(/extra configuration/i)).toHaveValue('{\n  "root_path": "/old"\n}');
    fireEvent.click(screen.getByLabelText(/embed tool output/i));
    fireEvent.change(screen.getByLabelText(/extra configuration/i), { target: { value: '{"root_path": "/new"}' } });
    fireEvent.submit(document.getElementById("mce-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ embed_output: true, config: { root_path: "/new" } });
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
