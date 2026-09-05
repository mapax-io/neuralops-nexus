import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { PersonasTab } from "./personas-tab";

const BASE = "http://server.test:8096";

const PROJECTS = [
  { id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] },
  { id: "p2", name: "Zephyr", slug: "zephyr", description: null, channels: [] },
];

// m1 is attached to Apollo; m2 only to Zephyr — the persona dialog must still
// offer m2 for Apollo via the attach-on-create group instead of dead-ending.
const MODELS = [
  { id: "m1", name: "House model", provider: "anthropic", model_id: "anthropic/claude-sonnet-5", api_base: null, description: null, temperature: 0.7, max_tokens: 4096, context_window: 200000, supports_tools: true, has_api_key: true, project_ids: ["p1"] },
  { id: "m2", name: "Spare model", provider: "openai", model_id: "openai/gpt-5", api_base: null, description: null, temperature: 0.7, max_tokens: 4096, context_window: 128000, supports_tools: true, has_api_key: true, project_ids: ["p2"] },
];

let attached: string[] = [];
let personaBody: Record<string, unknown> | null = null;

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

beforeEach(() => {
  attached = [];
  personaBody = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/personas/`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/ai-models/`, () => HttpResponse.json(MODELS)),
    http.get(`${BASE}/api/v1/agents/`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/mcp-servers/`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/output-types/`, () => HttpResponse.json([{ name: "text", label: "Text", icon: "", render_as: "text" }])),
    http.get(`${BASE}/api/v1/prompt-templates`, () => HttpResponse.json({ prompts: {} })),
    http.post(`${BASE}/api/v1/projects/:pid/ai-models/:mid/attach/`, ({ params }) => {
      attached.push(`${params.pid}:${params.mid}`);
      return HttpResponse.json({ ok: true });
    }),
    http.post(`${BASE}/api/v1/personas/`, async ({ request }) => {
      personaBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "per1", name: personaBody.name, description: null, project_id: personaBody.project_id, source_type: personaBody.source_type, model_id: personaBody.model_id ?? null, agent_id: null, prompt: null, avatar: null });
    }),
  );
});

describe("CreatePersonaDialog — project clarity", () => {
  it("owns its project: in-dialog select, project name in the title", async () => {
    renderTab();
    const dialog = await openCreate();
    // The title names the target project so there is no ambiguity.
    expect(within(dialog).getByRole("heading", { name: /new persona — apollo/i })).toBeInTheDocument();
    const select = within(dialog).getByLabelText("Project") as HTMLSelectElement;
    expect(select.value).toBe("p1");
    // Switching the project inside the dialog re-titles it live.
    fireEvent.change(select, { target: { value: "p2" } });
    expect(within(dialog).getByRole("heading", { name: /new persona — zephyr/i })).toBeInTheDocument();
  });
});

describe("CreatePersonaDialog — no dead ends", () => {
  it("offers unattached models and attaches them on create", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Layla" } });
    // m2 is not attached to Apollo but must still be pickable.
    fireEvent.change(within(dialog).getByLabelText("Model"), { target: { value: "m2" } });
    fireEvent.change(within(dialog).getByLabelText("Role"), { target: { value: "You are the analyst." } });
    fireEvent.submit(document.getElementById("pe-form")!);
    await waitFor(() => expect(personaBody).not.toBeNull());
    // Attach ran against the dialog's project before the persona was created.
    expect(attached).toEqual(["p1:m2"]);
    expect(personaBody).toMatchObject({ project_id: "p1", model_id: "m2", source_type: "model" });
  });

  it("ignores a second submit while the attach is still in flight", async () => {
    let personaPosts = 0;
    server.use(
      http.post(`${BASE}/api/v1/projects/:pid/ai-models/:mid/attach/`, async ({ params }) => {
        await new Promise((r) => setTimeout(r, 120)); // slow attach — the double-submit window
        attached.push(`${params.pid}:${params.mid}`);
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${BASE}/api/v1/personas/`, async ({ request }) => {
        personaPosts += 1;
        personaBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "per1", name: personaBody.name, description: null, project_id: personaBody.project_id, source_type: personaBody.source_type, model_id: personaBody.model_id ?? null, agent_id: null, prompt: null, avatar: null });
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
    // Give a trailing tick for any stray second create to land — it must not.
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

  it("offers inline agent creation when the project has no agents", async () => {
    renderTab();
    const dialog = await openCreate();
    fireEvent.click(within(dialog).getByRole("radio", { name: /agent — acts with tools/i }));
    fireEvent.click(within(dialog).getByRole("button", { name: /create an agent/i }));
    expect(await screen.findByRole("heading", { name: /new agent — apollo/i })).toBeInTheDocument();
  });
});
