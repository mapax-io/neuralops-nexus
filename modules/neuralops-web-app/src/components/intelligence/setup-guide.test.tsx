import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { grantAll, grantNone } from "@/test/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useUiStore } from "@/stores/ui.store";
import { IntelNav } from "./nav";

const BASE = "http://server.test:8096";
const PROJECTS = [{ id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] }, { id: "p2", name: "Zephyr", slug: "zephyr", description: null, channels: [] }];
const MODEL = { id: "m1", name: "House", provider: "anthropic", model_id: "claude-sonnet-5", qualified_id: "anthropic:claude-sonnet-5", api_base: null, description: null, licence_accepted: true, context_window: 200000, supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false, config: {}, is_active: true, has_api_key: true, project_ids: ["p1"] };
const MCP = { id: "s0", name: "Apollo Capabilities", description: null, project_id: "p1", is_internal: true, capability_config: { Filesystem: {} }, is_protected: true, is_default: true, server_type: "remote", transport: "http", url: null, command: null, docker_image: null, docker_command: null, kubernetes_service: null, timeout_seconds: 60, max_retries: 3, config: {}, is_first_party: false, embed_output: false, auth_type: "none", oauth_config: null, oauth_connected: false };
const PERSONA = { id: "pe1", name: "Layla", description: null, project_id: "p1", model: { id: "m1", name: "House", provider: "anthropic", model_id: "claude-sonnet-5", qualified_id: "anthropic:claude-sonnet-5", supports_tools: true }, advisor_model: null, mcp_servers: [], temperature: 0.7, max_tokens: 4096, max_steps: 10, prompt: null, is_active: true, avatar: null };

let models: unknown[] = [];
let mcp: unknown[] = [];
let personas: Record<string, unknown[]> = { p1: [], p2: [] };
const onSection = vi.fn();

function renderNav() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <IntelNav section="personas" onSection={onSection} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  onSection.mockClear();
  models = []; mcp = []; personas = { p1: [], p2: [] };
  useUiStore.setState({ intelProject: undefined, intelCreate: false });
  useConnectionStore.setState({
    serverUrl: BASE, token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    grantAll(BASE, { projects: ["p1", "p2"], topics: [] }),
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/model-configs/`, () => HttpResponse.json(models)),
    http.get(`${BASE}/api/v1/mcp-servers/`, () => HttpResponse.json(mcp)),
    http.get(`${BASE}/api/v1/personas/`, ({ request }) => HttpResponse.json(personas[new URL(request.url).searchParams.get("project_id") ?? ""] ?? [])),
  );
});

const steps = async () => within(await screen.findByRole("list", { name: "Setup steps" })).getAllByRole("listitem");

describe("SetupGuide — the nav footer says where you stand and what to do next", () => {
  it("on an empty workspace: every step open, the model step is the way in, the persona step waits for a model", async () => {
    renderNav();
    const items = await steps();
    expect(items).toHaveLength(3);
    expect(screen.getByText("0/3")).toBeInTheDocument();
    expect(screen.getByText(/setup — apollo/i)).toBeInTheDocument();
    expect(within(items[0]).getByRole("button", { name: /register a model/i })).toBeInTheDocument();
    expect(within(items[1]).getByRole("button", { name: /add tools/i })).toBeInTheDocument();
    expect(within(items[2]).queryByRole("button")).not.toBeInTheDocument();
    expect(within(items[2]).getByText(/needs a model first/i)).toBeInTheDocument();
    expect(screen.queryByText(/ready —/i)).not.toBeInTheDocument();
  });

  it("the action switches the section and opens its create dialog in one click", async () => {
    renderNav();
    const items = await steps();
    fireEvent.click(within(items[0]).getByRole("button", { name: /register a model/i }));
    expect(onSection).toHaveBeenCalledWith("models");
    expect(useUiStore.getState().intelCreate).toBe(true);
  });

  it("with a model and the project's default tools, only the persona is left — and it is actionable now", async () => {
    models = [MODEL]; mcp = [MCP];
    renderNav();
    const items = await steps();
    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(within(items[0]).getByLabelText("done")).toBeInTheDocument();
    expect(within(items[1]).getByLabelText("done")).toBeInTheDocument();
    fireEvent.click(within(items[2]).getByRole("button", { name: /new persona/i }));
    expect(onSection).toHaveBeenCalledWith("personas");
  });

  it("when everything is in place it tells you how to use it, naming a persona and the project", async () => {
    models = [MODEL]; mcp = [MCP]; personas = { p1: [PERSONA], p2: [] };
    renderNav();
    await steps();
    expect(screen.getByText("3/3")).toBeInTheDocument();
    expect(screen.getByText(/ready —/i)).toHaveTextContent(/@Layla/);
    expect(screen.getByText(/ready —/i)).toHaveTextContent(/Apollo/);
    expect(screen.queryByRole("button", { name: /new persona|register a model|add tools/i })).not.toBeInTheDocument();
  });

  it("follows the project the personas tab is looking at", async () => {
    models = [MODEL]; mcp = [MCP]; personas = { p1: [PERSONA], p2: [] };
    useUiStore.setState({ intelProject: "p2" });
    renderNav();
    const items = await steps();
    expect(screen.getByText(/setup — zephyr/i)).toBeInTheDocument();
    // Zephyr has no tools row and no persona: 1/3.
    await waitFor(() => expect(screen.getByText("1/3")).toBeInTheDocument());
    expect(within(items[2]).getByRole("button", { name: /new persona/i })).toBeInTheDocument();
  });

  it("offers no actions when none of the create rights are held — status only", async () => {
    server.use(grantNone(BASE));
    useConnectionStore.setState({ connection: { serverUrl: BASE, role: "member", isOwner: false, companyName: "Acme", serverVersion: "dev", moduleVersions: {} } });
    renderNav();
    const items = await steps();
    expect(items).toHaveLength(3);
    expect(screen.queryByRole("button", { name: /register a model|add tools|new persona/i })).not.toBeInTheDocument();
  });

  it("counts personas on the nav for the same project", async () => {
    models = [MODEL]; personas = { p1: [PERSONA, { ...PERSONA, id: "pe2", name: "Dev" }], p2: [] };
    renderNav();
    await steps();
    const nav = screen.getByRole("navigation", { name: "Intelligence sections" });
    expect(within(nav).getByRole("button", { name: /^personas/i })).toHaveTextContent("2");
  });
});
