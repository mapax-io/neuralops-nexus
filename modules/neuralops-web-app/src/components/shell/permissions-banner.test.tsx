import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { grantAll } from "@/test/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { PermissionsBanner } from "./permissions-banner";

const BASE = "http://server.test:8096";

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PermissionsBanner />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "owner", isOwner: true, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
});

describe("PermissionsBanner", () => {
  it("explains why controls are missing when the server has no permissions route", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 404 })));
    renderBanner();
    expect(await screen.findByRole("status")).toHaveTextContent(/server is out of date/i);
  });

  it("says nothing once the server answers", async () => {
    server.use(grantAll(BASE, { projects: ["p1"], topics: [] }));
    const { container } = renderBanner();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  // A failure is NOT an out-of-date server -- different cause, different
  // remedy. But it must still be explained: rendering every control hidden and
  // saying nothing is the bug this banner exists to prevent.
  it("explains a failed load and offers a retry, without blaming the server's version", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 500 })));
    renderBanner();
    const alert = await screen.findByRole("alert", {}, { timeout: 6000 });
    expect(alert).toHaveTextContent(/couldn.t load what you.re allowed to do/i);
    expect(alert).not.toHaveTextContent(/out of date/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  }, 12_000);

  it("recovers when the retry succeeds", async () => {
    let fail = true;
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () =>
      fail ? new HttpResponse(null, { status: 500 })
           : HttpResponse.json({ company: { id: "c1", rights: [] }, projects: {}, topics: {} })));
    const { container } = renderBanner();
    await screen.findByRole("alert", {}, { timeout: 6000 });
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(container).toBeEmptyDOMElement(), { timeout: 6000 });
  }, 12_000);

  it("stays quiet before a server is connected", async () => {
    useConnectionStore.setState({ serverUrl: null, token: null, connection: null });
    const { container } = renderBanner();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
