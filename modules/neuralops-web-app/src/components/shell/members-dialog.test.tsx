import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { MembersDialog } from "./members-dialog";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

const BASE = "http://server.test:8096";
let invited: Record<string, unknown> | null = null;

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MembersDialog open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  invited = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    email: "owner@acme.test",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(`${BASE}/api/v1/members/`, () => HttpResponse.json([{ user_id: "u1", email: "owner@acme.test", role: "owner", avatar: null, invited_by: null }])),
    http.post(`${BASE}/api/v1/members/invite/`, async ({ request }) => {
      invited = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ status: "invited", email: "new@acme.test", role: "member", message: "ok", email_sent: false });
    }),
  );
});

describe("MembersDialog — the invite form follows its rule", () => {
  it("keeps Invite disabled until the address is valid; a visited field explains itself live", async () => {
    renderDialog();
    fireEvent.click(await screen.findByRole("button", { name: /invite a teammate/i }));
    const dialog = screen.getByRole("dialog");
    const invite = within(dialog).getByRole("button", { name: /^invite$/i });
    expect(invite).toBeDisabled();
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument(); // a blank form is not covered in red
    const email = within(dialog).getByLabelText("Email");
    fireEvent.change(email, { target: { value: "not-an-address" } });
    expect(invite).toBeDisabled();
    fireEvent.blur(email);
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    fireEvent.change(email, { target: { value: "new@acme.test" } });
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
    expect(invite).toBeEnabled();
    fireEvent.click(invite);
    await waitFor(() => expect(invited).not.toBeNull());
    expect(invited).toMatchObject({ email: "new@acme.test", role: "member" });
  });
});
