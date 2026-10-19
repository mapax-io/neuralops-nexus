// device-request — a fresh install asks for a claim code.
// Called by nucleus (authn/portal.py request_device_code):
//   POST {"server_url": "..."}  →  {"code": "483-291", "request_id": "<uuid>", "expires_in": 900}
// The function name and response keys are nucleus's contract — do not rename.
// Deploy with "Verify JWT" ON (nucleus sends the anon key — see portal.py).
import { createClient } from "npm:@supabase/supabase-js@2";

const EXPIRES_IN = 900; // 15 minutes — matches nucleus's DEFAULT_EXPIRES_IN

const admin = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

function makeCode(): string {
  // 6 digits shown as 483-291 — easy to read off a screen and type.
  const n = crypto.getRandomValues(new Uint32Array(1))[0] % 1_000_000;
  const s = n.toString().padStart(6, "0");
  return `${s.slice(0, 3)}-${s.slice(3)}`;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return Response.json({ error: "POST only" }, { status: 405 });
  }
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch (_) {
    // an empty body is fine — server_url is informational
  }
  const server_url = String(body.server_url ?? "").slice(0, 500);

  // Insert, retrying on the rare pending-code collision (unique index).
  for (let attempt = 0; attempt < 5; attempt++) {
    const code = makeCode();
    const { data, error } = await admin
      .from("device_requests")
      .insert({ code, server_url })
      .select("id")
      .single();
    if (!error && data) {
      return Response.json({ code, request_id: data.id, expires_in: EXPIRES_IN });
    }
    if (error && !String(error.message).includes("device_requests_pending_code")) {
      console.error("device-request insert failed:", error.message);
      return Response.json({ error: "could not create a code" }, { status: 500 });
    }
  }
  return Response.json({ error: "could not create a unique code" }, { status: 500 });
});
