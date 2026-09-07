import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "./client";
import { useConnectivity } from "@/lib/connectivity";
import { useConnectionStore } from "@/stores/connection.store";

const fetchMock = vi.fn();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  useConnectivity.setState({ browserOnline: true, serverDown: false, serverDownSince: null });
  useConnectionStore.setState({ serverUrl: "http://server.test:8096", token: "jwt" });
});
afterEach(() => vi.unstubAllGlobals());

describe("apiJson reports the server's reachability", () => {
  it("a call that never arrives marks the server down; the next answer clears it", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(apiJson("/api/v1/x/")).rejects.toMatchObject({ status: 0 });
    expect(useConnectivity.getState().serverDown).toBe(true);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await expect(apiJson("/api/v1/x/")).resolves.toEqual({ ok: true });
    expect(useConnectivity.getState().serverDown).toBe(false);
  });

  it("a gateway answer with nothing behind it counts as down; an ordinary 4xx does not", async () => {
    fetchMock.mockResolvedValueOnce(new Response("<html>502</html>", { status: 502 }));
    await expect(apiJson("/api/v1/x/")).rejects.toMatchObject({ status: 502 });
    expect(useConnectivity.getState().serverDown).toBe(true);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Nope" }), { status: 403 }));
    await expect(apiJson("/api/v1/x/")).rejects.toMatchObject({ status: 403, message: "Nope" });
    expect(useConnectivity.getState().serverDown).toBe(false); // it answered — it is there
  });
});
