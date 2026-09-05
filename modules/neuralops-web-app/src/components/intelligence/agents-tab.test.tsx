import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { MCPServer } from "@/lib/api/intelligence";
import { AgentsTab } from "./agents-tab";

const BASE = "http://server.test:8096";

const PROJECTS = [
  { id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] },
];
const MODELS = [
  { id: "m1", name: "House model", provider: "anthropic", model_id: "anthropic/claude-sonnet-5", api_base: null, description: null, temperature: 0.7, max_tokens: 4096, context_window: 200000, supports_tools: true, has_api_key: true, project_ids: ["p1"] },
];
const AGENT = { id: "a0", name: "Existing", description: null, project_id: "p1", agent_type: "internal", model_id: "m1", model_name: "House model", mcp_server_id: null, mcp_server_name: null, safety_mode: true, max_steps: 5 };

let servers: MCPServer[] = [];

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentsTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  servers = [];
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/ai-models/`, () => HttpResponse.json(MODELS)),
    http.get(`${BASE}/api/v1/agents/`, () => HttpResponse.json([AGENT])),
    http.get(`${BASE}/api/v1/mcp-servers/`, () => HttpResponse.json(servers)),
    http.post(`${BASE}/api/v1/mcp-servers/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const created = {
        id: "s9", name: body.name, description: null, project_id: body.project_id,
        server_type: "remote", transport: "http", url: body.url, timeout_seconds: 60,
        embed_output: false, auth_type: "none", oauth_config: null, oauth_connected: false,
      } as MCPServer;
      servers = [...servers, created];
      return HttpResponse.json(created);
    }),
  );
});

describe("CreateAgentDialog — no dead ends", () => {
  it("offers both inline creations even before a project is picked", async () => {
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /new agent/i }));
    const dialog = screen.getByRole("dialog");
    // No project chosen yet ("Choose a project…") — the affordances must
    // still be there, or the dialog reads as a dead end again.
    expect((within(dialog).getByLabelText("Project") as HTMLSelectElement).value).toBe("");
    expect(within(dialog).getByRole("button", { name: /register a new model/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /add a tool server/i })).toBeInTheDocument();
  });

  it("adopts the created server's project when none was picked yet", async () => {
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /new agent/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /add a tool server/i }));
    const nested = (await screen.findByRole("heading", { name: /add an mcp tool server/i })).closest('[role="dialog"]') as HTMLElement;
    fireEvent.change(within(nested).getByLabelText("Project"), { target: { value: "p1" } });
    fireEvent.change(within(nested).getByLabelText("Name"), { target: { value: "Warehouse tools" } });
    fireEvent.change(within(nested).getByLabelText("URL"), { target: { value: "http://tools.internal:8080/mcp" } });
    fireEvent.submit(document.getElementById("mcp-form")!);
    await waitFor(() => expect((within(dialog).getByLabelText("Project") as HTMLSelectElement).value).toBe("p1"));
    await waitFor(() => expect((within(dialog).getByLabelText(/mcp server/i) as HTMLSelectElement).value).toBe("s9"));
  });

  it("clears project-scoped picks when the project changes", async () => {
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /new agent/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Project"), { target: { value: "p1" } });
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.change(within(dialog).getByLabelText("Project"), { target: { value: "" } });
    expect((within(dialog).getByLabelText("Model") as HTMLSelectElement).value).toBe("");
  });

  it("titles with the project and adds an MCP server inline, auto-selecting it", async () => {
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: /new agent/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Project"), { target: { value: "p1" } });
    expect(within(dialog).getByRole("heading", { name: /new agent — apollo/i })).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /add a tool server/i }));
    const mcpDialog = await screen.findByRole("heading", { name: /add an mcp tool server — apollo/i });
    const nested = mcpDialog.closest('[role="dialog"]') as HTMLElement;
    fireEvent.change(within(nested).getByLabelText("Name"), { target: { value: "Warehouse tools" } });
    fireEvent.change(within(nested).getByLabelText("URL"), { target: { value: "http://tools.internal:8080/mcp" } });
    fireEvent.submit(document.getElementById("mcp-form")!);

    // Nested dialog closes; the agent dialog now has the new server selected.
    await waitFor(() => expect(screen.queryByRole("heading", { name: /add an mcp tool server/i })).not.toBeInTheDocument());
    await waitFor(() => expect((within(dialog).getByLabelText(/mcp server/i) as HTMLSelectElement).value).toBe("s9"));
  });
});
