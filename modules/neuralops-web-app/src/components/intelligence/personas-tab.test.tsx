import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { MCPServer, ModelConfig, Persona } from "@/lib/api/intelligence";
import { PersonasTab } from "./personas-tab";

const BASE = "http://server.test:8096";

const PROJECTS = [
  { id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] },
  { id: "p2", name: "Zephyr", slug: "zephyr", description: null, channels: [] },
];

function model(over: Partial<ModelConfig> & Pick<ModelConfig, "id" | "name" | "provider" | "model_id">): ModelConfig {
  return {
    api_base: null, description: null, licence_accepted: true, context_window: 8192,
    supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false,
    config: {}, is_active: true, has_api_key: true, project_ids: ["p1"],
    qualified_id: `${over.provider}:${over.model_id}`,
    ...over,
  };
}
// m1 attached to Apollo; m2/m4 only to Zephyr (attach & use); m3 in Apollo but
// not tool-capable — the exact mix the server's wiring guards care about.
const MODELS = [
  model({ id: "m1", name: "House model", provider: "anthropic", model_id: "claude-sonnet-5" }),
  model({ id: "m2", name: "Spare model", provider: "openai", model_id: "gpt-5", project_ids: ["p2"] }),
  model({ id: "m3", name: "Chat only", provider: "ollama", model_id: "llama3", supports_tools: false, has_api_key: false }),
  model({ id: "m4", name: "Second spare", provider: "google", model_id: "gemini-2.0-flash", project_ids: ["p2"] }),
];

function mcp(id: string, name: string, over: Partial<MCPServer> = {}): MCPServer {
  return {
    id, name, description: null, project_id: "p1", server_type: "remote", transport: "http",
    url: `http://${id}.internal/mcp`, command: null, timeout_seconds: 60, max_retries: 3, config: {}, is_first_party: false, embed_output: false,
    auth_type: "none", oauth_config: null, oauth_connected: false, ...over,
  };
}

const ref = (m: ModelConfig) => ({ id: m.id, name: m.name, provider: m.provider, model_id: m.model_id, qualified_id: m.qualified_id, supports_tools: m.supports_tools });
const LAYLA: Persona = {
  id: "per0", name: "Layla", description: "Product analyst", project_id: "p1",
  model: ref(MODELS[0]), advisor_model: ref(MODELS[2]),
  mcp_servers: [
    { id: "s1", name: "Warehouse tools", transport: "http", auth_type: "none", oauth_connected: false },
    { id: "s2", name: "Jira", transport: "http", auth_type: "oauth2", oauth_connected: false },
  ],
  temperature: 0.3, max_tokens: 2048, max_steps: 12,
  prompt: { system_prompt: "You are the analyst.", output_type: "chart" },
  is_active: true, avatar: null,
};

let servers: MCPServer[] = [];
let modelList: ModelConfig[] = [];
let personas: Persona[] = [];
let attached: string[] = [];
let personaBody: Record<string, unknown> | null = null;
let patchBody: Record<string, unknown> | null = null;

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PersonasTab canManage />
    </QueryClientProvider>,
  );
}

async function openCreate() {
  fireEvent.click(await screen.findByRole("button", { name: /new persona/i }));
  return screen.getByRole("dialog");
}

async function openEdit(name: string) {
  fireEvent.click(await screen.findByRole("button", { name: `Edit persona ${name}` }));
  return screen.getByRole("dialog");
}

const toolBox = (scope: HTMLElement, name: string) => within(scope).getByRole("checkbox", { name }) as HTMLInputElement;

beforeEach(() => {
  servers = [mcp("s1", "Warehouse tools"), mcp("s2", "Jira", { auth_type: "oauth2" })];
  modelList = [...MODELS];
  personas = [];
  attached = [];
  personaBody = null;
  patchBody = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/personas/`, () => HttpResponse.json(personas)),
    http.get(`${BASE}/api/v1/model-configs/`, () => HttpResponse.json(modelList)),
    http.post(`${BASE}/api/v1/model-configs/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const created = model({ id: "m9", name: body.name as string, provider: body.provider as string, model_id: body.model_id as string, supports_tools: body.supports_tools as boolean, project_ids: [] });
      modelList = [...modelList, created];
      return HttpResponse.json(created);
    }),
    http.get(`${BASE}/api/v1/mcp-servers/`, () => HttpResponse.json(servers)),
    http.get(`${BASE}/api/v1/output-types/`, () => HttpResponse.json([{ name: "text", label: "Text", icon: "", render_as: "text" }, { name: "chart", label: "Chart", icon: "", render_as: "html" }])),
    http.get(`${BASE}/api/v1/prompt-templates`, () => HttpResponse.json({ prompts: { t1: "featured/Git_Master.md" } })),
    http.get(`${BASE}/api/v1/prompt-templates/t1`, () => HttpResponse.json({ content: "---\npersona_name: {PERSONA_NAME}\n---\nYou are {PERSONA_NAME}, the git expert." })),
    http.post(`${BASE}/api/v1/projects/:pid/model-configs/:mid/attach/`, ({ params }) => {
      attached.push(`${params.pid}:${params.mid}`);
      return HttpResponse.json({ ok: true });
    }),
    http.post(`${BASE}/api/v1/personas/`, async ({ request }) => {
      personaBody = (await request.json()) as Record<string, unknown>;
      const m = MODELS.find((x) => x.id === personaBody!.model_config_id)!;
      return HttpResponse.json({ ...LAYLA, id: "per1", name: personaBody.name, project_id: personaBody.project_id, model: ref(m), advisor_model: null, mcp_servers: [] });
    }),
    http.patch(`${BASE}/api/v1/personas/:id/`, async ({ request }) => {
      patchBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(LAYLA);
    }),
    http.post(`${BASE}/api/v1/mcp-servers/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const created = mcp("s9", body.name as string, { project_id: body.project_id as string, url: body.url as string });
      servers = [...servers, created];
      return HttpResponse.json(created);
    }),
  );
});

describe("PersonasTab — cards reflect the composition", () => {
  it("shows model, advisor and tool chips, flags a server needing reconnect, and counts in the toolbar", async () => {
    personas = [LAYLA];
    renderTab();
    await screen.findByText("@Layla");
    expect(screen.getByText("House model")).toBeInTheDocument();
    expect(screen.getByText(/advisor · Chat only/)).toBeInTheDocument();
    expect(screen.getByText("2 tools")).toBeInTheDocument();
    // Jira is oauth2 and not connected — the card must say so, not hide it.
    expect(screen.getByText(/reconnect needed/i)).toBeInTheDocument();
    expect(screen.getByText("12 steps")).toBeInTheDocument();
    expect(screen.getByText("temp 0.3")).toBeInTheDocument();
    for (const fact of ["1 persona", "1 with tools", "1 with an advisor"]) {
      expect(screen.getByText(fact)).toBeInTheDocument();
    }
  });
});

describe("CreatePersonaDialog — project clarity", () => {
  it("owns its project: in-dialog select, project name in the title", async () => {
    renderTab();
    const dialog = await openCreate();
    expect(within(dialog).getByRole("heading", { name: /new persona — apollo/i })).toBeInTheDocument();
    const select = within(dialog).getByLabelText("Project") as HTMLSelectElement;
    expect(select.value).toBe("p1");
    fireEvent.change(select, { target: { value: "p2" } });
    expect(within(dialog).getByRole("heading", { name: /new persona — zephyr/i })).toBeInTheDocument();
  });
});

describe("CreatePersonaDialog — required fields are marked", () => {
  it("marks exactly the fields a blank would block, in both dialogs", async () => {
    personas = [LAYLA];
    renderTab();
    const create = await openCreate();
    for (const field of ["Project", "Name", "Model", "Role", "Temperature", "Max tokens", "Max steps"]) {
      expect(within(create).getByLabelText(field)).toBeRequired();
      expect(within(create).getByText(field, { selector: "label" })).toHaveAttribute("data-required", "true");
    }
    for (const field of [/advisor model/i, /description/i, /default answer format/i]) {
      expect(within(create).getByLabelText(field)).not.toBeRequired();
    }
    fireEvent.keyDown(document, { key: "Escape" });
    const edit = await openEdit("Layla");
    for (const field of ["Name", "Model", "Role", "Max steps"]) expect(within(edit).getByLabelText(field)).toBeRequired();
    expect(within(edit).getByLabelText(/advisor model/i)).not.toBeRequired();
  });
});

describe("CreatePersonaDialog — name is mandatory", () => {
  it("keeps Create persona disabled until a name is typed", async () => {
    renderTab();
    const dialog = await openCreate();
    const create = within(dialog).getByRole("button", { name: /create persona/i });
    expect(create).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "   " } });
    expect(create).toBeDisabled(); // whitespace is not a name
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    expect(create).toBeEnabled();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "" } });
    expect(create).toBeDisabled();
  });
});

describe("CreatePersonaDialog — composition", () => {
  it("posts model, advisor, tool servers and generation settings in the server's shape", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.change(within(dialog).getByLabelText(/advisor model/i), { target: { value: "m3" } });
    fireEvent.click(toolBox(dialog, "Warehouse tools"));
    fireEvent.change(within(dialog).getByLabelText("Temperature"), { target: { value: "0.2" } });
    fireEvent.change(within(dialog).getByLabelText("Max tokens"), { target: { value: "1024" } });
    fireEvent.change(within(dialog).getByLabelText("Max steps"), { target: { value: "6" } });
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are the analyst." } });
    fireEvent.submit(document.getElementById("pe-form")!);
    await waitFor(() => expect(personaBody).not.toBeNull());
    expect(personaBody).toMatchObject({
      project_id: "p1", name: "Layla", model_config_id: "m1", advisor_model_config_id: "m3",
      mcp_server_ids: ["s1"], temperature: 0.2, max_tokens: 1024, max_steps: 6,
      prompt: { system_prompt: "You are the analyst.", output_type: "text" },
    });
    // The retired discriminator must not ride along.
    expect(personaBody).not.toHaveProperty("source_type");
    expect(personaBody).not.toHaveProperty("model_id");
    expect(attached).toEqual([]);
  });

  it("attaches an out-of-project primary AND advisor to the project before creating", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m2" } });
    fireEvent.change(within(dialog).getByLabelText(/advisor model/i), { target: { value: "m4" } });
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are the analyst." } });
    fireEvent.submit(document.getElementById("pe-form")!);
    await waitFor(() => expect(personaBody).not.toBeNull());
    expect(attached).toEqual(["p1:m2", "p1:m4"]);
    expect(personaBody).toMatchObject({ model_config_id: "m2", advisor_model_config_id: "m4" });
  });

  it("keeps the advisor distinct from the primary: excluded from the list, cleared if the primary takes its place", async () => {
    renderTab();
    const dialog = await openCreate();
    const advisor = within(dialog).getByLabelText(/advisor model/i) as HTMLSelectElement;
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    expect(within(advisor).queryByRole("option", { name: /house model/i })).not.toBeInTheDocument();
    fireEvent.change(advisor, { target: { value: "m3" } });
    expect(advisor.value).toBe("m3");
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m3" } });
    expect(advisor.value).toBe("");
    expect(within(advisor).queryByRole("option", { name: /chat only/i })).not.toBeInTheDocument();
  });

  it("disables tool servers for a model that can't call tools and unticks any picks", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.click(toolBox(dialog, "Warehouse tools"));
    expect(toolBox(dialog, "Warehouse tools").checked).toBe(true);
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m3" } });
    expect(toolBox(dialog, "Warehouse tools").checked).toBe(false);
    expect(toolBox(dialog, "Warehouse tools").disabled).toBe(true);
    expect(within(dialog).getByText(/isn't marked tool-capable/i)).toBeInTheDocument();
  });

  it("caps tool servers at five", async () => {
    servers = ["s1", "s2", "s3", "s4", "s5", "s6"].map((id) => mcp(id, `Server ${id}`));
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    for (const id of ["s1", "s2", "s3", "s4", "s5"]) fireEvent.click(toolBox(dialog, `Server ${id}`));
    expect(toolBox(dialog, "Server s6").disabled).toBe(true);
    expect(toolBox(dialog, "Server s1").disabled).toBe(false); // ticked ones stay untickable
    expect(within(dialog).getByText(/up to 5/i)).toBeInTheDocument();
  });

  it("ignores a second submit while the attach is still in flight", async () => {
    let personaPosts = 0;
    server.use(
      http.post(`${BASE}/api/v1/projects/:pid/model-configs/:mid/attach/`, async ({ params }) => {
        await new Promise((r) => setTimeout(r, 120)); // slow attach — the double-submit window
        attached.push(`${params.pid}:${params.mid}`);
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${BASE}/api/v1/personas/`, async ({ request }) => {
        personaPosts += 1;
        personaBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...LAYLA, id: "per1", name: personaBody.name, model: ref(MODELS[1]), advisor_model: null, mcp_servers: [] });
      }),
    );
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m2" } });
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are the analyst." } });
    fireEvent.submit(document.getElementById("pe-form")!);
    fireEvent.submit(document.getElementById("pe-form")!); // impatient Enter mid-attach
    await waitFor(() => expect(personaPosts).toBe(1));
    await new Promise((r) => setTimeout(r, 150));
    expect(personaPosts).toBe(1);
    expect(attached).toEqual(["p1:m2"]);
  });

  it("opens the model dialog inline via Register a new model", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.click(within(dialog).getByRole("button", { name: /register a new model/i }));
    expect(await screen.findByRole("heading", { name: /register an ai model — apollo/i })).toBeInTheDocument();
  });

  it("registers a model inline, picks it, and applies its tool capability before the list refreshes", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.click(toolBox(dialog, "Warehouse tools"));
    fireEvent.click(within(dialog).getByRole("button", { name: /register a new model/i }));
    const nested = (await screen.findByRole("heading", { name: /register an ai model — apollo/i })).closest('[role="dialog"]') as HTMLElement;
    fireEvent.change(within(nested).getByLabelText("Name"), { target: { value: "Chatty" } });
    fireEvent.change(within(nested).getByLabelText("Model id"), { target: { value: "claude-haiku-4-5" } });
    fireEvent.change(within(nested).getByLabelText("API key"), { target: { value: "sk-x" } });
    fireEvent.click(within(nested).getByLabelText(/supports tool use/i)); // registered WITHOUT tools
    fireEvent.click(within(nested).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(screen.queryByRole("heading", { name: /register an ai model/i })).not.toBeInTheDocument());
    await waitFor(() => expect((within(dialog).getByLabelText("Model") as HTMLSelectElement).value).toBe("m9"));
    // The new model can't call tools — the earlier tick was cleared, not left to 400 on submit.
    expect(toolBox(dialog, "Warehouse tools").checked).toBe(false);
    expect(within(dialog).getByText(/isn't marked tool-capable/i)).toBeInTheDocument();
    expect(attached).toEqual(["p1:m9"]); // registered from a project-scoped flow → attached there
  });

  it("explains an empty advisor list and registers a second model straight into the advisor slot", async () => {
    modelList = [MODELS[0]]; // the only model on the server
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    const advisor = within(dialog).getByLabelText(/advisor model/i) as HTMLSelectElement;
    // Nothing but "No advisor" is eligible — the user must be told why, not left guessing.
    expect(within(advisor).getAllByRole("option")).toHaveLength(1);
    expect(within(dialog).getByText(/already the primary/i)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /register a second model/i }));
    const nested = (await screen.findByRole("heading", { name: /register an ai model — apollo/i })).closest('[role="dialog"]') as HTMLElement;
    fireEvent.change(within(nested).getByLabelText("Name"), { target: { value: "Second opinion" } });
    fireEvent.change(within(nested).getByLabelText("Model id"), { target: { value: "claude-haiku-4-5" } });
    fireEvent.change(within(nested).getByLabelText("API key"), { target: { value: "sk-x" } });
    fireEvent.click(within(nested).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(screen.queryByRole("heading", { name: /register an ai model/i })).not.toBeInTheDocument());
    // The new model lands in the ADVISOR slot; the primary is untouched.
    await waitFor(() => expect(advisor.value).toBe("m9"));
    expect((within(dialog).getByLabelText("Model") as HTMLSelectElement).value).toBe("m1");
    expect(attached).toEqual(["p1:m9"]);
  });

  it("adds an MCP tool server inline and ticks it on return", async () => {
    renderTab();
    const dialog = await openCreate();
    // The block names the protocol — "tool servers" alone left users guessing.
    expect(within(dialog).getByText(/mcp tool servers/i, { selector: "legend" })).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /add an mcp tool server/i }));
    const nested = (await screen.findByRole("heading", { name: /add an mcp tool server — apollo/i })).closest('[role="dialog"]') as HTMLElement;
    fireEvent.change(within(nested).getByLabelText("Name"), { target: { value: "Ledger" } });
    fireEvent.change(within(nested).getByLabelText("URL"), { target: { value: "http://ledger.internal/mcp" } });
    fireEvent.submit(document.getElementById("mcp-form")!);
    await waitFor(() => expect(screen.queryByRole("heading", { name: /add an mcp tool server/i })).not.toBeInTheDocument());
    await waitFor(() => expect(toolBox(dialog, "Ledger").checked).toBe(true));
  });
});

describe("CreatePersonaDialog — {PERSONA_NAME} in templates", () => {
  it("fills the token with the typed name, live, whichever comes first", async () => {
    renderTab();
    const dialog = await openCreate();
    const role = within(dialog).getByLabelText("Role") as HTMLTextAreaElement;
    // Template first, name still blank → the token stays visible, with a hint.
    fireEvent.change(within(dialog).getByLabelText(/start from a template/i), { target: { value: "t1" } });
    await waitFor(() => expect(role.value).toContain("persona_name: {PERSONA_NAME}"));
    expect(within(dialog).getByText(/fills in with the name above/i)).toBeInTheDocument();
    // Typing the name replaces every token in what's shown.
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    expect(role.value).toBe("---\npersona_name: Layla\n---\nYou are Layla, the git expert.");
    // And keeps following the name until the role text is edited by hand.
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Lyla" } });
    expect(role.value).toContain("You are Lyla, the git expert.");
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.submit(document.getElementById("pe-form")!);
    await waitFor(() => expect(personaBody).not.toBeNull());
    expect(personaBody).toMatchObject({ name: "Lyla", prompt: { system_prompt: "---\npersona_name: Lyla\n---\nYou are Lyla, the git expert." } });
  });

  it("saves the name into a role written with the token by hand", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m1" } });
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are {PERSONA_NAME}." } });
    fireEvent.submit(document.getElementById("pe-form")!);
    await waitFor(() => expect(personaBody).not.toBeNull());
    expect(personaBody).toMatchObject({ prompt: { system_prompt: "You are Layla." } });
  });
});

describe("EditPersonaDialog — {PERSONA_NAME} in an existing role", () => {
  it("shows the token filled with the persona's name and saves it filled when the role changes", async () => {
    personas = [{ ...LAYLA, prompt: { system_prompt: "You are {PERSONA_NAME}.", output_type: "text" } }];
    renderTab();
    const dialog = await openEdit("Layla");
    const role = within(dialog).getByLabelText("Role") as HTMLTextAreaElement;
    expect(role.value).toBe("You are Layla.");
    fireEvent.submit(document.getElementById("pd-form")!);
    // Nothing typed → nothing sent; the stored role is left exactly as it was.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(patchBody).toBeNull();
  });

  it("sends the filled role once it is edited", async () => {
    personas = [{ ...LAYLA, prompt: { system_prompt: "You are {PERSONA_NAME}.", output_type: "text" } }];
    renderTab();
    const dialog = await openEdit("Layla");
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are Layla. Be brief." } });
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({ prompt: { system_prompt: "You are Layla. Be brief.", output_type: "text" } });
  });
});

describe("EditPersonaDialog — mutable backing", () => {
  beforeEach(() => {
    personas = [LAYLA];
  });

  it("disables Save changes while the name is cleared", async () => {
    renderTab();
    const dialog = await openEdit("Layla");
    const save = within(dialog).getByRole("button", { name: /save changes/i });
    expect(save).toBeEnabled();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "" } });
    expect(save).toBeDisabled();
  });

  it("pre-fills the composition and sends only what changed", async () => {
    renderTab();
    const dialog = await openEdit("Layla");
    expect((within(dialog).getByLabelText("Model") as HTMLSelectElement).value).toBe("m1");
    expect((within(dialog).getByLabelText(/advisor model/i) as HTMLSelectElement).value).toBe("m3");
    expect(toolBox(dialog, "Warehouse tools").checked).toBe(true);
    expect(toolBox(dialog, "Jira").checked).toBe(true);
    expect(within(dialog).getByLabelText("Temperature")).toHaveValue(0.3);
    expect(within(dialog).getByLabelText("Max tokens")).toHaveValue(2048);
    expect(within(dialog).getByLabelText("Max steps")).toHaveValue(12);
    fireEvent.change(within(dialog).getByLabelText("Temperature"), { target: { value: "0.9" } });
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({ temperature: 0.9 });
  });

  it("clears the advisor with clear_advisor and detaches every server with an empty list", async () => {
    renderTab();
    const dialog = await openEdit("Layla");
    fireEvent.change(within(dialog).getByLabelText(/advisor model/i), { target: { value: "" } });
    fireEvent.click(toolBox(dialog, "Warehouse tools"));
    fireEvent.click(toolBox(dialog, "Jira"));
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({ clear_advisor: true, mcp_server_ids: [] });
  });

  it("switching to a model without tool support unticks the servers and saves that honestly", async () => {
    renderTab();
    const dialog = await openEdit("Layla");
    // m3 is currently the advisor — it disappears from the advisor list and the
    // advisor is cleared, exactly as the server would otherwise refuse.
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m3" } });
    expect(toolBox(dialog, "Warehouse tools").checked).toBe(false);
    expect(toolBox(dialog, "Jira").disabled).toBe(true);
    expect(within(dialog).getByText(/isn't marked tool-capable/i)).toBeInTheDocument();
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({ model_config_id: "m3", clear_advisor: true, mcp_server_ids: [] });
  });

  it("attaches an out-of-project model before saving the swap", async () => {
    renderTab();
    const dialog = await openEdit("Layla");
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m2" } });
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(attached).toEqual(["p1:m2"]);
    expect(patchBody).toEqual({ model_config_id: "m2" });
  });

  it("closes without a request when nothing changed", async () => {
    renderTab();
    await openEdit("Layla");
    fireEvent.submit(document.getElementById("pd-form")!);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(patchBody).toBeNull();
  });
});
