import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { ApiError, absolutizeMedia, apiJson } from "./client";
import { useConnectionStore } from "@/stores/connection.store";

const BASE = "http://server.test:8096";

beforeEach(() => {
  useConnectionStore.setState({ serverUrl: BASE, token: "jwt-123" });
});

describe("apiJson", () => {
  it("joins the active server URL and sends the bearer token", async () => {
    let auth = "";
    server.use(
      http.get(`${BASE}/api/v1/projects/`, ({ request }) => {
        auth = request.headers.get("authorization") ?? "";
        return HttpResponse.json([{ id: "p1" }]);
      }),
    );
    const out = await apiJson<Array<{ id: string }>>("/api/v1/projects/");
    expect(out[0].id).toBe("p1");
    expect(auth).toBe("Bearer jwt-123");
  });

  it("returns undefined for 204 (DELETE endpoints have no body)", async () => {
    server.use(http.delete(`${BASE}/api/v1/personas/x/`, () => new HttpResponse(null, { status: 204 })));
    await expect(apiJson("/api/v1/personas/x/", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("normalizes error envelopes: detail, then message, then raw text", async () => {
    server.use(
      http.get(`${BASE}/api/v1/a/`, () => HttpResponse.json({ detail: "Project not found." }, { status: 404 })),
      http.get(`${BASE}/api/v1/b/`, () => HttpResponse.json({ message: "nope" }, { status: 400 })),
      http.get(`${BASE}/api/v1/c/`, () => new HttpResponse("plain failure", { status: 500 })),
    );
    await expect(apiJson("/api/v1/a/")).rejects.toMatchObject({ status: 404, message: "Project not found." });
    await expect(apiJson("/api/v1/b/")).rejects.toMatchObject({ status: 400, message: "nope" });
    await expect(apiJson("/api/v1/c/")).rejects.toMatchObject({ status: 500, message: "plain failure" });
  });

  it("throws status 0 when fetch itself fails (network / private-network block)", async () => {
    server.use(http.get(`${BASE}/api/v1/down/`, () => HttpResponse.error()));
    await expect(apiJson("/api/v1/down/")).rejects.toMatchObject({ status: 0 });
  });

  it("refuses to call without an active server", async () => {
    useConnectionStore.setState({ serverUrl: null, token: null });
    await expect(apiJson("/api/v1/projects/")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("absolutizeMedia", () => {
  it("prefixes server-relative media paths with the active server URL", () => {
    expect(absolutizeMedia("/media/avatars/a.png")).toBe(`${BASE}/media/avatars/a.png`);
  });
  it("leaves absolute URLs and empty values alone", () => {
    expect(absolutizeMedia("https://cdn.example/x.png")).toBe("https://cdn.example/x.png");
    expect(absolutizeMedia(null)).toBeNull();
  });
});

// A request that never answers (a server mid-restart during a deploy) must
// not hold a loader forever: it becomes the same "could not reach" failure a
// dropped connection is, which every gate already knows how to show.
describe("apiJson — a request that never answers gives up", () => {
  it("rejects after the timeout as an unreachable server", async () => {
    server.use(http.get(`${BASE}/api/v1/hang/`, () => new Promise<never>(() => {})));
    await expect(apiJson("/api/v1/hang/", { timeoutMs: 60 })).rejects.toMatchObject({ status: 0, message: "Could not reach the server." });
  });
});
