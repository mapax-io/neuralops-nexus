// device-claim — the SIGNED-IN person types the code from the install's screen.
// Called by the claim page (never by nucleus):
//   POST {"code": "483-291"}  with  Authorization: Bearer <the person's session token>
//   → {"ok": true, "server_url": "..."}  or  {"ok": false, "error": "..."}
// SECURITY (owner's ruling 2026-10-18, installer-only): claiming requires BOTH
// a verified signed-in person AND the code that exists only on the install's
// own screen. The function stores the person's token on the row; device-poll
// hands it to the install exactly once. This function can never create users
// or touch anyone's server — the install pulls and decides for itself.
// Deploy with "Verify JWT" ON.
import { createClient } from "npm:@supabase/supabase-js@2";

const admin = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") {
    return Response.json({ ok: false, error: "POST only" }, { status: 405, headers: CORS });
  }

  // Who is this? Verify the person's session token with Supabase auth.
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: userData, error: authError } = await admin.auth.getUser(token);
  if (authError || !userData?.user?.email) {
    return Response.json({ ok: false, error: "Please sign in first." },
      { status: 401, headers: CORS });
  }

  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch (_) { /* handled below */ }
  // Accept "483-291", "483291", with spaces — people type codes imperfectly.
  const raw = String(body.code ?? "").replace(/[^0-9]/g, "");
  if (raw.length !== 6) {
    return Response.json({ ok: false, error: "That doesn't look like a 6-digit code." },
      { status: 400, headers: CORS });
  }
  const code = `${raw.slice(0, 3)}-${raw.slice(3)}`;

  // Exactly one pending, unexpired request may carry this code (unique index).
  const { data: row } = await admin
    .from("device_requests")
    .select("id,server_url,expires_at")
    .eq("code", code)
    .eq("status", "pending")
    .maybeSingle();

  if (!row || new Date(row.expires_at) < new Date()) {
    return Response.json(
      { ok: false, error: "Code not found or expired — check the install's screen and try again." },
      { status: 404, headers: CORS });
  }

  const { error: updateError } = await admin
    .from("device_requests")
    .update({
      status: "claimed",
      access_token: token,
      claimed_email: userData.user.email,
    })
    .eq("id", row.id)
    .eq("status", "pending"); // claim races: first writer wins

  if (updateError) {
    console.error("device-claim update failed:", updateError.message);
    return Response.json({ ok: false, error: "Could not claim — try again." },
      { status: 500, headers: CORS });
  }
  return Response.json({ ok: true, server_url: row.server_url }, { headers: CORS });
});
