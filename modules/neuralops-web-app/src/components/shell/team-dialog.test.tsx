import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { Persona } from "@/lib/api/intelligence";
import { TeamDialog } from "./team-dialog";

const BASE = "http://server.test:8096";

const LAYLA: Persona = {
  id: "per0", name: "Layla", description: null, project_id: "p1",
  model: { id: "m1", name: "House model", provider: "anthropic", model_id: "claude-sonnet-5", qualified_id: "anthropic:claude-sonnet-5", supports_tools: true },
  advisor_model: null,
  mcp_servers: [
    { id: "s1", name: "Warehouse tools", transport: "http", auth_type: "none", oauth_connected: false },
    { id: "s2", name: "Jira", transport: "http", auth_type: "oauth2", oauth_connected: true },
  ],
  temperature: 0.7, max_tokens: 4096, max_steps: 10, prompt: null, is_active: true, avatar: null,
};

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TeamDialog pid="p1" projectName="Apollo" open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/projects/p1/team/`, () => HttpResponse.json([])),
    http.get(`${BASE}/api/v1/projects/p1/team/available-users/`, () => HttpResponse.json([])),
    // The server no longer sends source_type here — the row must describe the
    // persona from the project persona list instead of a retired discriminator.
    http.get(`${BASE}/api/v1/projects/p1/team/available-personas/`, () =>
      HttpResponse.json([{ persona_id: "per0", user_id: "u9", name: "Layla", avatar: null }]),
    ),
    http.get(`${BASE}/api/v1/personas/`, () => HttpResponse.json([LAYLA])),
  );
});

describe("TeamDialog — add persona", () => {
  it("describes an addable persona by its model and tool count", async () => {
    renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: "Add persona" }));
    // The roster above also lists every project persona, so the name shows
    // twice — the backing detail is what the add-row uniquely carries.
    expect(await screen.findByText("House model · 2 tools")).toBeInTheDocument();
    expect(screen.getAllByText("@Layla").length).toBeGreaterThan(0);
    expect(screen.queryByText(/model-backed|agent-backed/)).not.toBeInTheDocument();
  });
});
