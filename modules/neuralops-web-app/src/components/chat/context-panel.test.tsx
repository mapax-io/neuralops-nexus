import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useConnectionStore } from "@/stores/connection.store";
import { ContextPanel } from "./context-panel";

const BASE = "http://server.test:8096";
const PANEL_URL = `${BASE}/api/v1/projects/p1/topics/t1/context-panel/`;
const DELETE_URL = `${BASE}/api/v1/projects/p1/topics/t1/context-panel/items/`;

// Registry order is Files-then-Chat; the UI reorders so Chat History leads.
const PANEL = [
  {
    directive: "file",
    label: "Files",
    icon: "file-text",
    can_delete_source: false,
    can_delete_items: true,
    items: [
      { id: "f1", label: "q3-report.pdf", deletable: true, metadata: { status: "ready", size_kb: 12, type: "file" } },
      { id: "f2", label: "pricing.csv", deletable: true, metadata: { status: "ready", type: "file" } },
    ],
  },
  {
    directive: "chat",
    label: "Chat History",
    icon: "message-square",
    can_delete_source: false,
    can_delete_items: true,
    items: [{ id: "m1", label: "Backend numbers are in.", deletable: true, metadata: {} }],
  },
];

let deleteBody: { items: { directive: string; id: string }[] } | null = null;

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ContextPanel projectId="p1" topicId="t1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  deleteBody = null;
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "member", isOwner: false, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
  server.use(
    http.get(PANEL_URL, () => HttpResponse.json(PANEL)),
    http.delete(DELETE_URL, async ({ request }) => {
      deleteBody = (await request.json()) as typeof deleteBody;
      return HttpResponse.json({ ok: true, deleted: deleteBody!.items.map((i) => i.id) });
    }),
  );
});

describe("ContextPanel", () => {
  it("defaults to Chat History (leading tab), Files second", async () => {
    renderPanel();
    expect(await screen.findByRole("tab", { name: /Chat History/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Files/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("Backend numbers are in.")).toBeInTheDocument();
    // Leftmost tab is Chat History.
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAccessibleName(/Chat History/);
  });

  it("switching to Files shows file items with checkboxes", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("tab", { name: /Files/ }));
    expect(await screen.findByText("q3-report.pdf")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Select q3-report.pdf/ })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Select all/ })).toBeInTheDocument();
  });

  it("switching tabs clears the current selection", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select Backend numbers/ }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Files/ }));
    expect(await screen.findByText("q3-report.pdf")).toBeInTheDocument();
    expect(screen.queryByText("1 selected")).not.toBeInTheDocument();
  });

  it("select-all on Files checks every deletable item and shows the count", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("tab", { name: /Files/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select all/ }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Select q3-report.pdf/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: /Select pricing.csv/ })).toHaveAttribute("aria-checked", "true");
  });

  it("bulk-removes selected files via one batched DELETE (with directive)", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("tab", { name: /Files/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select q3-report.pdf/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Select pricing.csv/ }));
    fireEvent.click(screen.getByRole("button", { name: /Remove from context/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^Remove$/ }));
    await waitFor(() => expect(deleteBody).not.toBeNull());
    expect(deleteBody!.items).toEqual([
      { directive: "file", id: "f1" },
      { directive: "file", id: "f2" },
    ]);
  });

  it("chat-tab (default) removal sends the chat directive, not file", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select Backend numbers/ }));
    fireEvent.click(screen.getByRole("button", { name: /Remove from context/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^Remove$/ }));
    await waitFor(() => expect(deleteBody).not.toBeNull());
    expect(deleteBody!.items).toEqual([{ directive: "chat", id: "m1" }]);
  });

  it("keeps a per-row single delete with its own confirm dialog", async () => {
    renderPanel();
    // Default (Chat History) tab — click the row's own Remove (trash) button.
    fireEvent.click(await screen.findByRole("button", { name: /Remove Backend numbers.* from context/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Remove from context\?/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /^Remove$/ }));
    await waitFor(() => expect(deleteBody).not.toBeNull());
    expect(deleteBody!.items).toEqual([{ directive: "chat", id: "m1" }]);
  });

  it("offers Add file/link on the DEFAULT (Chat History) tab — no dead end", async () => {
    renderPanel();
    // Default tab is Chat History, but a Files group exists → adding is still offered.
    expect(await screen.findByRole("tab", { name: /Chat History/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: /Add file/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add link/ })).toBeInTheDocument();
  });

  it("keeps the last-loaded panel (with a retry) when a refetch fails — no blanking", async () => {
    let calls = 0;
    server.use(
      http.get(PANEL_URL, () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json(PANEL) : HttpResponse.error();
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ContextPanel projectId="p1" topicId="t1" />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Backend numbers are in.")).toBeInTheDocument();
    // Force a refetch that will fail.
    await qc.refetchQueries({ queryKey: ["context-panel"] });
    // Panel content survives (not blanked); a slim "couldn't refresh" retry shows.
    expect(await screen.findByText(/Couldn't refresh/)).toBeInTheDocument();
    expect(screen.getByText("Backend numbers are in.")).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load the context panel/)).not.toBeInTheDocument();
  });

  it("select-all is indeterminate (aria-checked=mixed) when only some are selected", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("tab", { name: /Files/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select q3-report.pdf/ }));
    // one of two selected → the select-all box is mixed
    expect(screen.getByRole("checkbox", { name: /Select all/ })).toHaveAttribute("aria-checked", "mixed");
  });

  it("a non-deletable item shows no checkbox", async () => {
    server.use(
      http.get(PANEL_URL, () =>
        HttpResponse.json([
          PANEL[1],
          { ...PANEL[0], items: [{ id: "f9", label: "readonly.pdf", deletable: false, metadata: { status: "ready" } }] },
        ]),
      ),
    );
    renderPanel();
    fireEvent.click(await screen.findByRole("tab", { name: /Files/ }));
    expect(await screen.findByText("readonly.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Select readonly.pdf/ })).not.toBeInTheDocument();
    // …and with nothing selectable, no Select-all either.
    expect(screen.queryByRole("checkbox", { name: /Select all/ })).not.toBeInTheDocument();
  });

  it("shows a per-tab empty state", async () => {
    server.use(
      http.get(PANEL_URL, () =>
        HttpResponse.json([PANEL[0], { ...PANEL[1], items: [] }]),
      ),
    );
    renderPanel();
    // Default tab (Chat History) is empty here.
    expect(await screen.findByText("No chat history in context")).toBeInTheDocument();
  });
});

describe("ContextPanel — the add-link form follows its rules", () => {
  it("keeps Add to context disabled until the address is a URL; a visited field explains itself live", async () => {
    // The form lives on the Web tab, which exists once the panel has a web group.
    server.use(http.get(PANEL_URL, () => HttpResponse.json([...PANEL, { directive: "web", label: "Web", icon: "globe", can_delete_source: true, can_delete_items: true, items: [] }])));
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /add link/i }));
    const add = screen.getByRole("button", { name: /add to context/i });
    expect(add).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // a blank form is not covered in red
    const url = screen.getByLabelText("Web address");
    fireEvent.change(url, { target: { value: "example.com" } });
    expect(add).toBeDisabled();
    fireEvent.blur(url);
    expect(screen.getByRole("alert")).toHaveTextContent(/valid URL/);
    fireEvent.change(url, { target: { value: "https://example.com/report" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(add).toBeEnabled();
    // An optional label still has to be a sane one once given.
    const name = screen.getByLabelText(/^name/i);
    fireEvent.change(name, { target: { value: "<script>" } });
    expect(add).toBeDisabled();
    fireEvent.blur(name);
    expect(screen.getByRole("alert")).toHaveTextContent(/letters, numbers/);
  });
});
