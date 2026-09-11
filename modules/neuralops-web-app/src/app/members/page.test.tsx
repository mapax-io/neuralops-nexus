import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { grantAll } from "@/test/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelectionStore } from "@/stores/selection.store";
import MembersPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/members",
}));

const BASE = "http://server.test:8096";
let membersHits = 0;
let sent: Record<string, unknown> | null = null;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MembersPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  membersHits = 0;
  sent = null;
  useSelectionStore.setState({ byServer: {} });
  useConnectionStore.setState({
    hydrated: true,
    serverUrl: BASE,
    token: "jwt",
    email: "owner@acme.test",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    grantAll(BASE, { projects: ["p1"], topics: [] }),
    http.get(`${BASE}/api/v1/auth/verify/`, () => HttpResponse.json({
      ok: true, email: "owner@acme.test", user_id: "u1", is_new_user: false,
      company_exists: true, is_owner: true, role: "owner", company_name: "Acme", server_version: "dev",
    })),
    http.get(`${BASE}/api/v1/members/`, () => {
      membersHits += 1;
      return HttpResponse.json([{ user_id: "u1", email: "owner@acme.test", role: "owner", avatar: null, invited_by: null, joined_at: "2026-09-01T00:00:00Z" }]);
    }),
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json([
      { id: "p1", name: "Alpha", slug: "alpha", description: null, channels: [{ id: "c1", name: "general", slug: "general", description: null }] },
    ])),
    http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => HttpResponse.json([
      { id: "t1", title: "chat#1", slug: "chat-1", channel_id: "c1", project_id: "p1" },
    ])),
    http.post(`${BASE}/api/v1/members/invite/`, async ({ request }) => {
      sent = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ok: true, email: "new@acme.test", role: String(sent.role), message: "ok", grants: sent.grants ?? [] });
    }),
  );
});

// The page's dialog composes the same hook and fields as the header dialog;
// this proves the page wiring — footer buttons outside the form, refetch on
// success — carries the picks through.
describe("MembersPage — Invite teammate", () => {
  it("sends a whole-project grant with the picked role and refreshes the list", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /invite teammate/i }));
    const dialog = await screen.findByRole("dialog");
    const invite = within(dialog).getByRole("button", { name: /^invite$/i });
    expect(invite).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: "new@acme.test" } });
    fireEvent.change(within(dialog).getByLabelText("Company role"), { target: { value: "viewer" } });
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "Add to Alpha" }));
    expect(invite).toBeEnabled();
    const before = membersHits;
    fireEvent.click(invite);
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({ email: "new@acme.test", role: "viewer", grants: [{ project_id: "p1", topic_ids: [] }] });
    await waitFor(() => expect(membersHits).toBeGreaterThan(before));
  });

  it("without a pick still sends the plain server invite", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /invite teammate/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: "new@acme.test" } });
    await within(dialog).findByRole("checkbox", { name: "Add to Alpha" });
    fireEvent.click(within(dialog).getByRole("button", { name: /^invite$/i }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({ email: "new@acme.test", role: "member" });
    expect(sent).not.toHaveProperty("grants");
  });
});
