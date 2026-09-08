import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useConnectivity } from "@/lib/connectivity";
import { useConnectionStore } from "@/stores/connection.store";
import { ConnectivityBanner } from "./connectivity-banner";

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), warning: (...a: unknown[]) => toastWarning(...a), error: (...a: unknown[]) => toastError(...a) } }));

const BASE = "http://server.test:8096";
const fetchMock = vi.fn();

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConnectivityBanner />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastWarning.mockReset();
  toastError.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  useConnectivity.setState({ browserOnline: true, serverDown: false, serverDownSince: null });
  useConnectionStore.setState({
    serverUrl: BASE,
    token: "jwt",
    connection: { serverUrl: BASE, role: "member", isOwner: false, companyName: "Acme", serverVersion: "dev", moduleVersions: {} },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("ConnectivityBanner", () => {
  it("says nothing while everything is reachable", () => {
    renderBanner();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("names the server that stopped answering, and clears itself when Retry now gets through", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200 });
    renderBanner();
    act(() => useConnectivity.getState().reportServerFailure());
    expect(screen.getByRole("alert")).toHaveTextContent(/can't reach acme/i);
    fireEvent.click(screen.getByRole("button", { name: /retry now/i }));
    await waitFor(() => expect(useConnectivity.getState().serverDown).toBe(false));
    expect(fetchMock).toHaveBeenCalledWith(`${BASE}/api/v1/auth/config/`, expect.objectContaining({ cache: "no-store" }));
    expect(toastSuccess).toHaveBeenCalledWith("Connected to Acme again.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a gateway answer (nginx up, nucleus down) does not count as back", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502 });
    renderBanner();
    act(() => useConnectivity.getState().reportServerFailure());
    fireEvent.click(screen.getByRole("button", { name: /retry now/i }));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Still can't reach Acme."));
    expect(useConnectivity.getState().serverDown).toBe(true);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("follows the browser's own network: offline shows the notice and warns once, online clears it", async () => {
    renderBanner();
    await act(async () => {
      Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByRole("status")).toHaveTextContent(/you're offline/i);
    expect(toastWarning).toHaveBeenCalledTimes(1);
    await act(async () => {
      Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(toastSuccess).toHaveBeenCalledWith("You're back online.");
  });
});
