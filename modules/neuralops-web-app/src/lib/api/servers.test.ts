import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { connectToServer, fetchServerConfig } from "./servers";

const URL_ = "http://box.test:8096";

describe("fetchServerConfig", () => {
  it("returns version info from the public config endpoint", async () => {
    server.use(
      http.get(`${URL_}/api/v1/auth/config/`, () =>
        HttpResponse.json({ server_url: URL_, server_version: "0.1.2", nucleus_version: "1" }),
      ),
    );
    const cfg = await fetchServerConfig(URL_);
    expect(cfg?.server_version).toBe("0.1.2");
  });
  it("returns null when unreachable (never throws — used for card previews)", async () => {
    server.use(http.get(`${URL_}/api/v1/auth/config/`, () => HttpResponse.error()));
    await expect(fetchServerConfig(URL_)).resolves.toBeNull();
  });
});

describe("connectToServer — outcome taxonomy", () => {
  const verify = (body: object, status = 200) =>
    server.use(http.get(`${URL_}/api/v1/auth/verify/`, () => HttpResponse.json(body, { status })));

  it("succeeds with connection details on 200 ok", async () => {
    verify({
      ok: true,
      user_id: "u1",
      email: "a@b.c",
      company_exists: true,
      is_owner: true,
      role: "owner",
      company_name: "Acme",
      server_version: "0.1.2",
      nucleus_version: "1",
      nexus_ai_version: "2",
      nexus_transport_version: "6",
    });
    const out = await connectToServer(URL_, "jwt");
    expect(out.kind).toBe("ok");
    if (out.kind === "ok") {
      expect(out.connection.companyName).toBe("Acme");
      expect(out.connection.moduleVersions.nucleus).toBe("1");
      expect(out.isNewUser).toBe(false); // absent → not new
    }
  });

  it("carries the server's first-connect flag so the launcher can welcome a new member", async () => {
    verify({ ok: true, user_id: "u2", email: "n@b.c", is_new_user: true, company_exists: true, is_owner: false, role: "member", company_name: "Acme", server_version: "0.1.2" });
    const out = await connectToServer(URL_, "jwt");
    expect(out.kind === "ok" && out.isNewUser).toBe(true);
  });

  it("maps 403 to not-a-member", async () => {
    verify({ detail: "no" }, 403);
    expect((await connectToServer(URL_, "jwt")).kind).toBe("not-member");
  });

  it("maps company_exists=false to not-set-up", async () => {
    verify({ ok: true, company_exists: false, user_id: "u", email: "e" });
    expect((await connectToServer(URL_, "jwt")).kind).toBe("not-set-up");
  });

  it("maps fetch failure (status 0) to unreachable — the private-network case", async () => {
    server.use(http.get(`${URL_}/api/v1/auth/verify/`, () => HttpResponse.error()));
    expect((await connectToServer(URL_, "jwt")).kind).toBe("unreachable");
  });
});
