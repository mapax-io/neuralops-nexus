import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

  // A 500 is transient — blaming the server's version would be wrong, and the
  // query keeps retrying.
  it("stays quiet on a transient failure", async () => {
    server.use(http.get(`${BASE}/api/v1/me/permissions/`, () => new HttpResponse(null, { status: 500 })));
    const { container } = renderBanner();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("stays quiet before a server is connected", async () => {
    useConnectionStore.setState({ serverUrl: null, token: null, connection: null });
    const { container } = renderBanner();
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
