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
  is_internal: false,
  capability_config: {},
  is_protected: false,
  is_default: false,
  server_type: "remote",
  transport: "http",
  url: "http://tools.internal:8080/mcp",
  command: null,
  docker_image: null,
  docker_command: null,
  kubernetes_service: null,
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

// #104: one table, two kinds. An internal row is built-in capabilities the AI
// worker provides in-process (capability_config only); the row project
// provisioning creates is the project's default and cannot be removed.
const S0: MCPServer = {
  ...S1,
  id: "s0",
  name: "Apollo Capabilities",
  description: null,
  is_internal: true,
  is_protected: true,
  is_default: true,
  capability_config: { Filesystem: { root_dir: "/nexus/projects/apollo" }, Shell: { cwd: "/nexus/projects/apollo", allowed_commands: ["ls"] }, "Web Search": { local: "duckduckgo" }, "Web Fetch": { local: true } },
  url: null,
  auth_type: "none",
};

describe("McpTab — built-in (internal) capabilities", () => {
  it("shows a built-in row with its capabilities, a default badge, and a lock instead of a remove action", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([S0, S1])));
    renderTab();
    await screen.findByText("Apollo Capabilities");
    expect(screen.getByText("built-in")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText("Filesystem · Shell · Web search · Web fetch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove MCP server Apollo Capabilities" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /apollo capabilities is this project's default and cannot be removed/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit MCP server Apollo Capabilities" })).toBeInTheDocument();
    // The external row keeps its remove action.
    expect(screen.getByRole("button", { name: "Remove MCP server Warehouse tools" })).toBeInTheDocument();
    expect(screen.getByText("1 external")).toBeInTheDocument();
    expect(screen.getByText("1 built-in")).toBeInTheDocument();
  });

  it("a non-default built-in row can still be removed", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([{ ...S0, id: "s9", name: "Extra caps", is_protected: false, is_default: false }])));
    renderTab();
    await screen.findByText("Extra caps");
    fireEvent.click(screen.getByRole("button", { name: "Remove MCP server Extra caps" }));
    expect(screen.getByText("Remove these built-in capabilities?")).toBeInTheDocument();
  });

  it("adds built-in capabilities: no transport or URL, the four project defaults ticked, and posts only the internal fields", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fireEvent.click(screen.getByLabelText(/built-in capabilities/i));
    expect(screen.queryByLabelText("Transport")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("URL")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Timeout (seconds)")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Filesystem/)).toBeChecked();
    expect(screen.getByLabelText(/^Web fetch/)).toBeChecked();
    fireEvent.click(screen.getByLabelText(/^Shell/)); // off
    fireEvent.click(screen.getByLabelText(/^Thinking/)); // on
    fireEvent.change(screen.getByLabelText("Effort"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "p2" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Research caps" } });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({
      project_id: "p2", name: "Research caps", is_internal: true,
      capability_config: expect.objectContaining({ Filesystem: expect.any(Object), "Web Search": { local: "duckduckgo" }, "Web Fetch": { local: true }, Thinking: { effort: "high" } }),
    });
    expect((posted!.capability_config as Record<string, unknown>).Shell).toBeUndefined();
    expect(posted).not.toHaveProperty("url");
    expect(posted).not.toHaveProperty("transport");
    expect(posted).not.toHaveProperty("auth_type");
  });

  it("refuses an internal row with every capability off", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fireEvent.click(screen.getByLabelText(/built-in capabilities/i));
    for (const rx of [/^Filesystem/, /^Shell/, /^Web search/, /^Web fetch/]) fireEvent.click(screen.getByLabelText(rx));
    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Nothing" } });
    submitCreate();
    await screen.findByText("Turn on at least one capability.");
    expect(posted).toBeNull();
  });

  it("edits a built-in row: kind fixed, only the changed capability_config is patched", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([S0])));
    let patched: Record<string, unknown> | null = null;
    server.use(http.patch(`${SERVERS_URL}:id/`, async ({ request }) => { patched = (await request.json()) as Record<string, unknown>; return HttpResponse.json({ ...S0, ...patched }); }));
    renderTab();
    await screen.findByText("Apollo Capabilities");
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Apollo Capabilities" }));
    await screen.findByText("Edit Apollo Capabilities");
    expect(screen.getByText(/built-in capabilities — this project's default/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("URL")).not.toBeInTheDocument();
    expect(screen.queryByText(/transport/i)).not.toBeInTheDocument();
    fireEvent.submit(document.getElementById("mce-form")!); // nothing changed → no request, dialog closes
    expect(patched).toBeNull();
    await waitFor(() => expect(screen.queryByText("Edit Apollo Capabilities")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Apollo Capabilities" }));
    await screen.findByText("Edit Apollo Capabilities");
    fireEvent.click(screen.getByLabelText(/^Web fetch/)); // off
    fireEvent.submit(document.getElementById("mce-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(Object.keys(patched!)).toEqual(["capability_config"]);
    expect(patched!.capability_config).toEqual({ Filesystem: { root_dir: "/nexus/projects/apollo" }, Shell: { cwd: "/nexus/projects/apollo", allowed_commands: ["ls"] }, "Web Search": { local: "duckduckgo" } });
  });
});

describe("McpTab — where an external server runs (server_type)", () => {
  it("follows the transport until chosen, then shows the Docker or Kubernetes fields and posts them", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    const runs = screen.getByLabelText("Runs as") as HTMLSelectElement;
    expect(runs.value).toBe("remote");
    fireEvent.change(screen.getByLabelText("Transport"), { target: { value: "stdio" } });
    expect(runs.value).toBe("local");
    fireEvent.change(screen.getByLabelText("Transport"), { target: { value: "http" } });
    fireEvent.change(runs, { target: { value: "docker" } });
    fireEvent.change(screen.getByLabelText("Docker image"), { target: { value: "ghcr.io/acme/mcp:1" } });
    fireEvent.change(screen.getByLabelText(/container command/i), { target: { value: "mcp --port 8080" } });
    fillCreate({ projectId: "p2", name: "Container tools", url: "http://mcp.internal:8080/mcp" });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ server_type: "docker", transport: "http", url: "http://mcp.internal:8080/mcp", docker_image: "ghcr.io/acme/mcp:1", docker_command: "mcp --port 8080" });
    expect(posted).not.toHaveProperty("kubernetes_service");
  });

  it("posts the Kubernetes service for a cluster runtime", async () => {
    renderTab();
    await screen.findByText("Warehouse tools");
    await openCreateDialog();
    fireEvent.change(screen.getByLabelText("Runs as"), { target: { value: "kubernetes" } });
    expect(screen.queryByLabelText("Docker image")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Kubernetes service"), { target: { value: "mcp.default.svc" } });
    fillCreate({ projectId: "p2", name: "Cluster tools", url: "http://mcp.default.svc/mcp" });
    submitCreate();
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ server_type: "kubernetes", kubernetes_service: "mcp.default.svc" });
  });

  it("shows the runtime as fixed on edit and patches only a changed container command", async () => {
    server.use(http.get(SERVERS_URL, () => HttpResponse.json([{ ...S1, id: "s4", name: "Container tools", server_type: "docker", docker_image: "ghcr.io/acme/mcp:1", docker_command: "mcp" }])));
    let patched: Record<string, unknown> | null = null;
    server.use(http.patch(`${SERVERS_URL}:id/`, async ({ request }) => { patched = (await request.json()) as Record<string, unknown>; return HttpResponse.json({ ...S1, ...patched }); }));
    renderTab();
    await screen.findByText("Container tools");
    fireEvent.click(screen.getByRole("button", { name: "Edit MCP server Container tools" }));
    await screen.findByText("Edit Container tools");
    expect(screen.getByText("Docker container")).toBeInTheDocument();
    expect(screen.queryByLabelText("Runs as")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Docker image")).toHaveValue("ghcr.io/acme/mcp:1");
    fireEvent.change(screen.getByLabelText(/container command/i), { target: { value: "mcp --verbose" } });
    fireEvent.submit(document.getElementById("mce-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ docker_command: "mcp --verbose" });
  });
});
