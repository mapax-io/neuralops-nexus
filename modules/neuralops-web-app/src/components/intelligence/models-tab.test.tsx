import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { grantAll } from "@/test/permissions";
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
      <ModelsTab />
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
    grantAll(BASE, { projects: ["p1", "p2"], topics: [] }),
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
      // Tool use is the only capability asked at registration and defaults on (the
      // server would default it OFF, which blocks MCP attachment); the rest is left
      // to the server and adjustable in Edit.
      supports_tools: true, context_window: 128000,
    });
    expect(posted).not.toHaveProperty("supports_streaming");
    expect(posted).not.toHaveProperty("supports_vision");
    expect(posted).not.toHaveProperty("supports_audio");
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

describe("ModelsTab — register asks only about tool use", () => {
  it("offers a ticked tool-use box and no other capability on register, but all four on edit", async () => {
    renderTab();
    const dialog = await openRegister();
    expect(within(dialog).getByLabelText(/supports tool use/i)).toBeChecked();
    for (const rx of [/streams responses/i, /understands images/i, /understands audio/i]) {
      expect(within(dialog).queryByLabelText(rx)).not.toBeInTheDocument();
    }
    expect(within(dialog).getByLabelText(/accept the model provider/i)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const edit = screen.getByRole("dialog");
    expect(within(edit).getByLabelText(/supports tool use/i)).toBeChecked();
    expect(within(edit).getByLabelText(/streams responses/i)).toBeChecked();
    expect(within(edit).getByLabelText(/understands images/i)).not.toBeChecked();
    expect(within(edit).getByLabelText(/understands audio/i)).not.toBeChecked();
  });

  it("posts supports_tools false when the box is unticked — a chat-only model must not be mistaken for a tool model", async () => {
    renderTab();
    const dialog = await openRegister();
    fireEvent.change(within(dialog).getByLabelText("Provider"), { target: { value: "ollama" } });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Chat only" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "llama3" } });
    fireEvent.click(within(dialog).getByLabelText(/supports tool use/i));
    fireEvent.click(within(dialog).getByLabelText(/accept the model provider/i));
    fireEvent.submit(document.getElementById("m-form")!);
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toMatchObject({ provider: "ollama", model_id: "llama3", supports_tools: false });
  });
});

describe("ModelsTab — no browser credential autofill in the model dialogs", () => {
  it("keeps saved logins out of the register dialog's fields", async () => {
    renderTab();
    const dialog = await openRegister();
    const key = within(dialog).getByLabelText("API key");
    expect(key).toHaveAttribute("autocomplete", "new-password");
    expect(key).toHaveAttribute("data-1p-ignore");
    expect(key).toHaveAttribute("data-lpignore", "true");
    // The text fields Chrome would pair with the password as a "username".
    expect(within(dialog).getByLabelText("Name")).toHaveAttribute("autocomplete", "off");
    expect(within(dialog).getByLabelText("Model id")).toHaveAttribute("autocomplete", "off");
  });

  it("and out of the edit dialog's key rotation field", async () => {
    renderTab();
    await screen.findByText("House model");
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const edit = screen.getByRole("dialog");
    const key = within(edit).getByLabelText(/api key/i);
    expect(key).toHaveAttribute("autocomplete", "new-password");
    expect(key).toHaveAttribute("data-1p-ignore");
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

describe("ModelsTab — the Register button follows every rule", () => {
  it("stays disabled until name, model id, key and terms are given; a visited field explains itself live", async () => {
    renderTab();
    const dialog = await openRegister();
    const register = within(dialog).getByRole("button", { name: /register model/i });
    expect(register).toBeDisabled();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument(); // a blank form is not covered in red
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "House" } });
    fireEvent.change(within(dialog).getByLabelText("Model id"), { target: { value: "sonnet-latest" } });
    expect(register).toBeDisabled(); // the provider needs a key, and the terms
    fireEvent.blur(within(dialog).getByLabelText("API key"));
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument(); // pristine and empty: quiet
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "sk-1" } });
    fireEvent.blur(within(dialog).getByLabelText("API key"));
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "" } });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This provider needs an API key."); // judged once: live
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "sk-1" } });
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
    expect(register).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText(/accept the model provider/i));
    expect(register).toBeEnabled();
    fireEvent.change(within(dialog).getByLabelText("Context window"), { target: { value: "0" } });
    expect(register).toBeDisabled();
    fireEvent.blur(within(dialog).getByLabelText("Context window"));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Must be at least 1.");
  });

  it("a submit that slips past the button reveals every unmet rule instead of posting", async () => {
    renderTab();
    const dialog = await openRegister();
    fireEvent.submit(document.getElementById("m-form")!);
    const alerts = within(dialog).getAllByRole("alert").map((a) => a.textContent);
    expect(alerts).toEqual(expect.arrayContaining(["Enter a model name.", "Enter the model id.", "This provider needs an API key.", "You must accept the provider's terms to register the model."]));
    expect(posted).toBeNull();
  });
});

// The model id field offers the provider's current models from OpenRouter's
// public catalog. The catalog is advisory: the field is free text with or
// without it, and it must never be swapped out from under a typing user.
const CATALOG_URL = "https://openrouter.ai/api/v1/models";
const CATALOG = {
  data: [
    { id: "anthropic/claude-sonnet-5", name: "Anthropic: Claude Sonnet 5" },
    { id: "anthropic/claude-haiku-4.5", name: "Anthropic: Claude Haiku 4.5" },
    { id: "openai/gpt-5", name: "OpenAI: GPT-5" },
    { id: "google/gemini-2.5-pro", name: "Google: Gemini 2.5 Pro" },
  ],
};

describe("ModelsTab — model id suggestions", () => {
  it("lists the picked provider's models as the user types, and a click fills the bare id", async () => {
    server.use(http.get(CATALOG_URL, () => HttpResponse.json(CATALOG)));
    renderTab();
    const dialog = await openRegister();
    const id = within(dialog).getByRole("combobox", { name: "Model id" });
    expect(id).toBeRequired();
    fireEvent.focus(id);
    fireEvent.change(id, { target: { value: "son" } });
    const list = await screen.findByRole("listbox");
    expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["Claude Sonnet 5claude-sonnet-5"]);
    fireEvent.mouseDown(within(list).getByRole("option", { name: /sonnet/i }));
    expect(id).toHaveValue("claude-sonnet-5");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    // The context window follows the picked id like a typed one.
    expect(within(dialog).getByLabelText(/context window/i)).toHaveValue(200000);
  });

  it("keeps the same field, and the user's focus, when the catalog arrives mid-typing", async () => {
    let release: (() => void) | null = null;
    server.use(http.get(CATALOG_URL, async () => {
      await new Promise<void>((r) => { release = r; });
      return HttpResponse.json(CATALOG);
    }));
    renderTab();
    const dialog = await openRegister();
    const id = within(dialog).getByLabelText("Model id");
    id.focus();
    fireEvent.change(id, { target: { value: "claude-s" } });
    await waitFor(() => expect(release).not.toBeNull());
    release!();
    await screen.findByRole("listbox");
    expect(within(dialog).getByLabelText("Model id")).toBe(id);
    expect(id).toHaveFocus();
    expect(id).toHaveValue("claude-s");
  });

  it("offers nothing for a provider the catalog does not cover, and never asks for the catalog before the dialog opens", async () => {
    let asked = 0;
    server.use(http.get(CATALOG_URL, () => { asked += 1; return HttpResponse.json(CATALOG); }));
    renderTab();
    await screen.findByRole("button", { name: /register model/i });
    expect(asked).toBe(0);
    const dialog = await openRegister();
    await waitFor(() => expect(asked).toBe(1));
    fireEvent.change(within(dialog).getByLabelText("Provider"), { target: { value: "ollama" } });
    const id = within(dialog).getByLabelText("Model id");
    fireEvent.focus(id);
    fireEvent.change(id, { target: { value: "l" } });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it.each([
    ["the catalog is down", () => new HttpResponse(null, { status: 503 })],
    ["the catalog answers with an unexpected shape", () => HttpResponse.json({ models: "nope" })],
  ])("stays a plain field when %s", async (_, answer) => {
    server.use(http.get(CATALOG_URL, answer));
    renderTab();
    const dialog = await openRegister();
    const id = within(dialog).getByLabelText("Model id");
    fireEvent.focus(id);
    fireEvent.change(id, { target: { value: "claude-sonnet-5" } });
    expect(id).toHaveValue("claude-sonnet-5");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("suggests on edit too, from the model's own provider", async () => {
    server.use(http.get(CATALOG_URL, () => HttpResponse.json(CATALOG)));
    renderTab();
    await screen.findByText("House model");
    fireEvent.click(screen.getByRole("button", { name: "Edit model House model" }));
    const dialog = screen.getByRole("dialog");
    const id = within(dialog).getByRole("combobox", { name: "Model id" });
    fireEvent.change(id, { target: { value: "haiku" } });
    const list = await screen.findByRole("listbox");
    fireEvent.mouseDown(within(list).getByRole("option", { name: /haiku/i }));
    expect(id).toHaveValue("claude-haiku-4.5");
  });
});
