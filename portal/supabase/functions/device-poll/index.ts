// device-poll — the install asks "has anyone typed my code yet?"
// Called by nucleus (authn/portal.py poll_device_code):
//   POST {"request_id": "<uuid>"}  →
//     {"status": "pending"}                     while nobody typed it
//     {"status": "claimed", "access_token": ...} ONCE, the moment it was typed
//     {"status": "expired"}                      when the 15 minutes passed
// SECURITY: the request_id is an unguessable uuid only the install holds —
// knowing the 6-digit code is NOT enough to poll. The token is handed out
// exactly once (consumed on read), then erased from the row.
// Deploy with "Verify JWT" ON (nucleus sends the anon key).
import { createClient } from "npm:@supabase/supabase-js@2";

const admin = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return Response.json({ error: "POST only" }, { status: 405 });
  }
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch (_) { /* handled below */ }
  const request_id = String(body.request_id ?? body.device_code ?? "");
  if (!request_id) {
    return Response.json({ status: "denied" });
  }

  const { data: row } = await admin
    .from("device_requests")
    .select("id,status,access_token,expires_at")
    .eq("id", request_id)
    .maybeSingle();

  if (!row || row.status === "consumed") {
    // unknown id, or a token already handed out: nothing more to give
    return Response.json({ status: "denied" });
  }
  if (row.status === "pending" && new Date(row.expires_at) < new Date()) {
    await admin.from("device_requests")
      .update({ status: "expired" }).eq("id", row.id);
    return Response.json({ status: "expired" });
  }
  if (row.status === "claimed" && row.access_token) {
    // one-time handover: consume and ERASE the token from the row
    await admin.from("device_requests")
      .update({ status: "consumed", access_token: null }).eq("id", row.id);
    return Response.json({ status: "claimed", access_token: row.access_token });
  }
  if (row.status === "expired") {
    return Response.json({ status: "expired" });
  }
  return Response.json({ status: "pending" });
});
