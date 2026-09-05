import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { ModelConfig } from "@/lib/api/intelligence";
import { ModelsTab } from "./models-tab";

const BASE = "http://server.test:8096";
const URL = `${BASE}/api/v1/model-configs/`;

const HOUSE: ModelConfig = {
  id: "m1", name: "House model", provider: "anthropic", model_id: "claude-sonnet-5", qualified_id: "anthropic:claude-sonnet-5",
  api_base: null, description: null, licence_accepted: true, context_window: 200000,
  supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false,
  config: {}, is_active: true, has_api_key: true, project_ids: ["p1"],
};

let posted: Record<string, unknown> | null = null;
let patched: Record<string, unknown> | null = null;

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ModelsTab canManage />
    </QueryClientProvider>,
  );
}

async function openRegister() {
  fireEvent.click(await screen.findByRole("button", { name: /register model/i }));
  return screen.getByRole("dialog");
}

beforeEach(() => {
  posted = null;
  patched = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(URL, () => HttpResponse.json([HOUSE])),
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([{ id: "p1", name: "Apollo", slug: "apollo", description: null, channels: [] }])),
    http.post(URL, async ({ request }) => {
      posted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...HOUSE, id: "m2", ...posted, qualified_id: `${posted.provider}:${posted.model_id}` });
    }),
    http.patch(`${URL}:id/`, async ({ request }) => {
      patched = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...HOUSE, ...patched });
    }),
  );
});

describe("ModelsTab — cards", () => {
  it("shows the qualified id the server composes from provider + bare model id", async () => {
    renderTab();
    await screen.findByText("House model");
    expect(screen.getByText("anthropic:claude-sonnet-5")).toBeInTheDocument();
  });
});

describe("ModelsTab — register", () => {
  it("rejects a provider-prefixed id and posts the bare id with its provider", async () => {
    renderTab();
    const dialog = await openRegister();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Mini" } });
    fireEvent.change(within(dialog).getByLabelText("Provider"), { target: { value: "openai" } });
    const id = within(dialog).getByLabelText("Model id");
    fireEvent.change(id, { target: { value: "openai/gpt-4o-mini" } });
    fireEvent.blur(id);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/bare model name/i);
    fireEvent.change(id, { target: { value: "gpt-4o-mini" } });
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(within(dialog).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({
      name: "Mini", provider: "openai", model_id: "gpt-4o-mini", api_key: "sk-test", licence_accepted: true,
      // gpt-4o-mini is a known family — the context window defaulted from the id, not the server's 8192.
      supports_tools: true, supports_streaming: true, supports_vision: false, supports_audio: false, context_window: 128000,
    });
    expect(posted).not.toHaveProperty("api_base");
  });

  it("also refuses the pydantic-ai colon form", async () => {
    renderTab();
    const dialog = await openRegister();
    const id = within(dialog).getByLabelText("Model id");
    fireEvent.change(id, { target: { value: "anthropic:claude-sonnet-5" } });
    fireEvent.blur(id);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/bare model name/i);
  });

  it("requires an API base for an OpenAI-compatible endpoint and sends it", async () => {
    renderTab();
    const dialog = await openRegister();
    fireEvent.change(within(dialog).getByLabelText("Provider"), { target: { value: "openai_compatible" } });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Local vLLM" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "qwen2.5-7b" } });
    fireEvent.click(within(dialog).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    expect(await within(dialog).findByText("Enter the API base URL.")).toBeInTheDocument();
    expect(posted).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(/api base/i), { target: { value: "http://vllm.internal:8000/v1" } });
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ provider: "openai_compatible", model_id: "qwen2.5-7b", api_base: "http://vllm.internal:8000/v1" });
  });

  it("offers exactly the server's five providers", async () => {
    renderTab();
    const dialog = await openRegister();
    const options = within(within(dialog).getByLabelText("Provider")).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    expect(options).toEqual(["anthropic", "openai", "google", "ollama", "openai_compatible"]);
  });
});

describe("ModelsTab — register carries the description", () => {
  it("posts the description when given, and omits it when blank", async () => {
    renderTab();
    const dialog = await openRegister();
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Fast" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "claude-haiku-4-5" } });
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "sk-x" } });
    fireEvent.change(within(dialog).getByLabelText(/description/i), { target: { value: "Cheap and quick" } });
    fireEvent.click(within(dialog).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ description: "Cheap and quick" });
  });
});

describe("ModelsTab — context window follows the model id", () => {
  it("fills the known size for the typed id, resets to the default for an unknown one, and keeps a hand-typed value", async () => {
    renderTab();
    const dialog = await openRegister();
    const ctx = within(dialog).getByLabelText("Context window") as HTMLInputElement;
    expect(ctx.value).toBe("8192");
    fireEvent.change(within(dialog).getByLabelText("Provider", { exact: true }), { target: { value: "openai" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "gpt-4o-mini" } });
    expect(ctx.value).toBe("128000");
    expect(within(dialog).getByText(/defaulted from the model id/i)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "totally-unknown" } });
    expect(ctx.value).toBe("8192");
    // Once the user types a size, the id stops overriding it.
    fireEvent.change(ctx, { target: { value: "65536" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "gpt-4o" } });
    expect(ctx.value).toBe("65536");
  });
});

describe("ModelsTab — required fields are marked", () => {
  it("follows the provider: key required for hosted providers, API base for compatible endpoints", async () => {
    renderTab();
    const dialog = await openRegister();
    for (const field of ["Name", "Model id", "API key", "Context window"]) expect(within(dialog).getByLabelText(field)).toBeRequired();
    expect(within(dialog).getByLabelText("Provider", { exact: true })).not.toBeRequired();
    fireEvent.change(within(dialog).getByLabelText("Provider", { exact: true }), { target: { value: "ollama" } });
    expect(within(dialog).getByLabelText(/api key/i)).not.toBeRequired();
    expect(within(dialog).getByLabelText(/api base/i)).not.toBeRequired();
    fireEvent.change(within(dialog).getByLabelText("Provider", { exact: true }), { target: { value: "openai_compatible" } });
    expect(within(dialog).getByLabelText(/api base/i)).toBeRequired();
    expect(within(dialog).getByText(/api base/i, { selector: "label" })).toHaveAttribute("data-required", "true");
  });
});

describe("ModelsTab — edit", () => {
  it("lets provider and model id change — warning that every persona follows — and refuses a prefixed id", async () => {
    renderTab();
    await screen.findByText("House model");
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Provider", { exact: true })).toHaveValue("anthropic");
    expect(within(dialog).getByLabelText("Model id")).toHaveValue("claude-sonnet-5");
    expect(within(dialog).getByText(/every persona on this model follows/i)).toBeInTheDocument();
    const id = within(dialog).getByLabelText("Model id");
    fireEvent.change(id, { target: { value: "anthropic/claude-opus-5" } });
    fireEvent.blur(id);
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/bare model name/i);
    fireEvent.change(id, { target: { value: "claude-opus-5" } });
    fireEvent.change(within(dialog).getByLabelText("Provider", { exact: true }), { target: { value: "openai_compatible" } });
    fireEvent.change(within(dialog).getByLabelText(/api base/i), { target: { value: "https://proxy.example.com/v1" } });
    fireEvent.submit(document.getElementById("me-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ provider: "openai_compatible", model_id: "claude-opus-5", api_base: "https://proxy.example.com/v1" });
  });

  it("patches only what changed, rotating the key when given", async () => {
    renderTab();
    await screen.findByText("House model");
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "House model v2" } });
    fireEvent.change(within(dialog).getByLabelText("Context window"), { target: { value: "100000" } });
    fireEvent.change(within(dialog).getByLabelText(/new api key/i), { target: { value: "sk-rotated" } });
    fireEvent.click(within(dialog).getByLabelText(/understands images/i));
    fireEvent.submit(document.getElementById("me-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ name: "House model v2", context_window: 100000, api_key: "sk-rotated", supports_vision: true });
  });

  it("never sends the key when the rotation field is left blank", async () => {
    renderTab();
    await screen.findByText("House model");
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/description/i), { target: { value: "Primary reasoning model" } });
    fireEvent.submit(document.getElementById("me-form")!);
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ description: "Primary reasoning model" });
  });
});
