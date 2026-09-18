import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import type { Member } from "@/lib/api/members";
import { MemberAccessDialog } from "./member-access-dialog";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const BASE = "http://server.test:8096";
const PROJECTS = [
  {
    id: "p1", name: "Alpha", slug: "alpha", description: null,
    channels: [{ id: "c1", name: "general", slug: "general", description: null }],
  },
  { id: "p2", name: "Beta", slug: "beta", description: null, channels: [] },
];
const topic = (id: string, title: string) => ({ id, title, slug: title, channel_id: "c1", project_id: "p1" });
const sara: Member = { user_id: "u2", email: "sara@acme.test", role: "member", invited_by: null, joined_at: "2026-09-02T00:00:00Z", avatar: null };

let access: Record<string, unknown>;
let saved: Record<string, unknown> | null = null;
let onSaved = 0;

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemberAccessDialog member={sara} open onClose={() => {}} onSaved={() => { onSaved += 1; }} />
    </QueryClientProvider>,
  );
}

const dialog = () => screen.getByRole("dialog");
const saveButton = () => within(dialog()).getByRole("button", { name: /save/i });

beforeEach(() => {
  saved = null;
  onSaved = 0;
  access = { user_id: "u2", role: "member", server_wide: false, grants: [{ project_id: "p1", topic_ids: ["t1"] }] };
  useConnectionStore.setState({ serverUrl: BASE, token: "jwt" });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => HttpResponse.json([topic("t1", "chat#1"), topic("t2", "chat#2")])),
    http.get(`${BASE}/api/v1/members/u2/access/`, () => HttpResponse.json(access)),
    http.put(`${BASE}/api/v1/members/u2/access/`, async ({ request }) => {
      saved = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ user_id: "u2", role: saved.role, server_wide: (saved.grants as unknown[]).length === 0, grants: saved.grants });
    }),
  );
});

describe("MemberAccessDialog — shows what they hold, saves only a real change", () => {
  it("loads a scoped member into the role select and the tree, with Save disabled", async () => {
    renderDialog();
    expect(await within(dialog()).findByLabelText("Company role")).toHaveValue("member");
    expect(within(dialog()).getByText(/applies only in the projects and topics picked below/i)).toBeInTheDocument();
    expect(await within(dialog()).findByRole("checkbox", { name: "Add to Alpha" })).toHaveAttribute("aria-checked", "mixed");
    // A row with picks starts open, so what they hold is visible without a click.
    expect(await within(dialog()).findByRole("checkbox", { name: "Add to chat#1" })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog()).getByRole("checkbox", { name: "Add to chat#2" })).toHaveAttribute("aria-checked", "false");
    expect(saveButton()).toBeDisabled();
  });

  it("shows a server-wide member with nothing picked", async () => {
    access = { user_id: "u2", role: "admin", server_wide: true, grants: [] };
    renderDialog();
    expect(await within(dialog()).findByLabelText("Company role")).toHaveValue("admin");
    expect(within(dialog()).getByText(/applies across the whole server/i)).toBeInTheDocument();
    expect(await within(dialog()).findByRole("checkbox", { name: "Add to Alpha" })).toHaveAttribute("aria-checked", "false");
    expect(within(dialog()).getByTestId("invite-summary")).toHaveTextContent("No project picked");
  });

  it("a changed role saves as a full replace and reports back", async () => {
    renderDialog();
    fireEvent.change(await within(dialog()).findByLabelText("Company role"), { target: { value: "viewer" } });
    expect(saveButton()).toBeEnabled();
    fireEvent.click(saveButton());
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toEqual({ role: "viewer", grants: [{ project_id: "p1", topic_ids: ["t1"] }] });
    await waitFor(() => expect(onSaved).toBe(1));
  });

  it("unticking everything widens them to the whole server — sent as no grants", async () => {
    renderDialog();
    fireEvent.click(await within(dialog()).findByRole("checkbox", { name: "Add to chat#1" }));
    expect(within(dialog()).getByText(/applies across the whole server/i)).toBeInTheDocument();
    fireEvent.click(saveButton());
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved).toEqual({ role: "member", grants: [] });
  });

  it("a change undone is not a change", async () => {
    renderDialog();
    const role = await within(dialog()).findByLabelText("Company role");
    fireEvent.change(role, { target: { value: "viewer" } });
    fireEvent.change(role, { target: { value: "member" } });
    expect(saveButton()).toBeDisabled();
  });

  it("shows the server's refusal and keeps the draft", async () => {
    server.use(http.put(`${BASE}/api/v1/members/u2/access/`, () => HttpResponse.json({ detail: "The owner's access cannot be changed." }, { status: 400 })));
    renderDialog();
    fireEvent.change(await within(dialog()).findByLabelText("Company role"), { target: { value: "admin" } });
    fireEvent.click(saveButton());
    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("owner's access cannot be changed");
    expect(within(dialog()).getByLabelText("Company role")).toHaveValue("admin");
    expect(onSaved).toBe(0);
  });

  it("reports a failed load with a retry", async () => {
    let fail = true;
    server.use(http.get(`${BASE}/api/v1/members/u2/access/`, () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(access))));
    renderDialog();
    const alert = await within(dialog()).findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load their access.");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: /retry/i }));
    expect(await within(dialog()).findByLabelText("Company role")).toBeInTheDocument();
  });
});
