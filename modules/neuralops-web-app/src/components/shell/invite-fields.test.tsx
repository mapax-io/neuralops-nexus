import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { useInvite } from "@/hooks/use-invite";
import { InviteFields } from "./invite-fields";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const BASE = "http://server.test:8096";
const PROJECTS = [
  {
    id: "p1", name: "Alpha", slug: "alpha", description: null,
    channels: [
      { id: "c1", name: "general", slug: "general", description: null },
      { id: "c2", name: "design", slug: "design", description: null },
    ],
  },
  { id: "p2", name: "Beta", slug: "beta", description: null, channels: [] },
];
const topic = (id: string, title: string, cid: string) => ({ id, title, slug: title, channel_id: cid, project_id: "p1" });

let sent: Record<string, unknown> | null = null;
let done = 0;
// What the server answers; a test can drop `grants` to play an old server.
let reply: () => Record<string, unknown>;

// The two real surfaces (members page, members dialog) compose exactly this:
// the hook owns the state, the fields render it, the host places the buttons.
function Harness() {
  const inv = useInvite({ onDone: () => { done += 1; } });
  return (
    <form onSubmit={inv.submit} noValidate>
      <InviteFields inv={inv} idPrefix="t" />
      <button type="submit" disabled={inv.invalid}>Send</button>
    </form>
  );
}

function renderHarness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
  return qc;
}

const typeEmail = (v = "new@acme.test") => fireEvent.change(screen.getByLabelText("Email"), { target: { value: v } });
const send = () => fireEvent.click(screen.getByRole("button", { name: "Send" }));
const tick = async (name: string) => fireEvent.click(await screen.findByRole("checkbox", { name }));
const open = async (name: string) => fireEvent.click(await screen.findByRole("button", { name, expanded: false }));

beforeEach(() => {
  sent = null;
  done = 0;
  vi.mocked(toast.error).mockClear();
  reply = () => ({ ok: true, email: "new@acme.test", role: "member", message: "new@acme.test added.", grants: (sent?.grants as unknown[]) ?? [] });
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    email: "owner@acme.test",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/projects/`, () => HttpResponse.json(PROJECTS)),
    http.get(`${BASE}/api/v1/projects/p1/channels/c1/topics/`, () => HttpResponse.json([topic("t1", "chat#1", "c1"), topic("t2", "chat#2", "c1")])),
    http.get(`${BASE}/api/v1/projects/p1/channels/c2/topics/`, () => HttpResponse.json([topic("t3", "chat#3", "c2")])),
    http.post(`${BASE}/api/v1/members/invite/`, async ({ request }) => {
      sent = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(reply());
    }),
  );
});

describe("InviteFields — what goes to the server", () => {
  it("with nothing picked, sends the plain server-wide invite — no grants key at all", async () => {
    renderHarness();
    typeEmail();
    await screen.findByRole("checkbox", { name: "Add to Alpha" });
    expect(screen.getByText(/applies across the whole server/i)).toBeInTheDocument();
    send();
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({ email: "new@acme.test", role: "member", redirect_to: expect.stringContaining("/reset-password") });
    expect(sent).not.toHaveProperty("grants");
    await waitFor(() => expect(done).toBe(1));
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("a ticked project is a whole-project grant, with the picked role, and the hint says it is scoped", async () => {
    renderHarness();
    typeEmail();
    fireEvent.change(screen.getByLabelText("Company role"), { target: { value: "admin" } });
    await tick("Add to Alpha");
    expect(screen.getByText(/applies only in the projects and topics picked below/i)).toBeInTheDocument();
    send();
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toMatchObject({ role: "admin", grants: [{ project_id: "p1", topic_ids: [] }] });
  });

  it("ticked topics are a topic-scoped grant; several projects are several grants", async () => {
    renderHarness();
    typeEmail();
    await tick("Add to Beta");
    await open("Alpha");
    await tick("Add to chat#2");
    send();
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent!.grants).toEqual([
      { project_id: "p2", topic_ids: [] },
      { project_id: "p1", topic_ids: ["t2"] },
    ]);
  });

  it("after a sent invite the form is clean, including the picks", async () => {
    renderHarness();
    typeEmail();
    await tick("Add to Beta");
    send();
    await waitFor(() => expect(done).toBe(1));
    expect(screen.getByLabelText("Email")).toHaveValue("");
    expect(screen.getByRole("checkbox", { name: "Add to Beta" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("No project picked");
  });

  it("shows the server's refusal under the form and keeps everything typed and picked", async () => {
    server.use(http.post(`${BASE}/api/v1/members/invite/`, () =>
      HttpResponse.json({ detail: "Topic t9 was not found in project 'Alpha'." }, { status: 400 })));
    renderHarness();
    typeEmail();
    await tick("Add to Alpha");
    send();
    expect(await screen.findByRole("alert")).toHaveTextContent("was not found in project 'Alpha'");
    expect(screen.getByLabelText("Email")).toHaveValue("new@acme.test");
    expect(screen.getByRole("checkbox", { name: "Add to Alpha" })).toHaveAttribute("aria-checked", "true");
    expect(done).toBe(0);
  });

  // A server from before grants existed ignores the field and hands out
  // server-wide access; the inviter must hear that, not a success.
  it("calls out a server that ignored the picks", async () => {
    reply = () => ({ ok: true, email: "new@acme.test", role: "member", message: "new@acme.test added." });
    renderHarness();
    typeEmail();
    await tick("Add to Beta");
    send();
    await waitFor(() => expect(done).toBe(1));
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/out of date/i), expect.anything());
  });

  it("does not raise that alarm for a plain invite, which every server understands", async () => {
    reply = () => ({ ok: true, email: "new@acme.test", role: "member", message: "ok" });
    renderHarness();
    typeEmail();
    await screen.findByRole("checkbox", { name: "Add to Alpha" });
    send();
    await waitFor(() => expect(done).toBe(1));
    expect(toast.error).not.toHaveBeenCalled();
  });

  // A project archived while the form was open: never send an id the server
  // will refuse, and never quietly send a wider (or narrower) invite instead.
  it("refuses to send when a pick has vanished, puts the picks back in step, and says so", async () => {
    const qc = renderHarness();
    typeEmail();
    await tick("Add to Beta");
    await tick("Add to Alpha");
    qc.setQueryData(["projects", BASE], PROJECTS.filter((p) => p.id === "p1")); // Beta is gone
    send();
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer on this server");
    expect(sent).toBeNull();
    expect(done).toBe(0);
    // Alpha survives, Beta is dropped from the picks; the summary agrees.
    expect(screen.getByRole("checkbox", { name: "Add to Alpha" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("invite-summary")).toHaveTextContent("Alpha (whole project)");
    expect(screen.getByTestId("invite-summary")).not.toHaveTextContent("Beta");
  });

  it("refreshes the roster of every project they were added to", async () => {
    const qc = renderHarness();
    qc.setQueryData(["team", BASE, "p1"], []);
    qc.setQueryData(["team", BASE, "p2"], []);
    typeEmail();
    await tick("Add to Alpha");
    await tick("Add to Beta");
    send();
    await waitFor(() => expect(done).toBe(1));
    expect(qc.getQueryState(["team", BASE, "p1"])?.isInvalidated).toBe(true);
    expect(qc.getQueryState(["team", BASE, "p2"])?.isInvalidated).toBe(true);
  });
});
