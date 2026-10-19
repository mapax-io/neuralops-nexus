// phone-home — the collector for the one value that ever leaves an install.
// Called by nucleus (core/phone_home.py, wired in core/asgi.py):
//   POST {"install_token": "...", "event": "open" | "close", "total_tokens": 12345}
//   → {"ok": true}   (any 2xx means "received" to nucleus)
// Stores one row per report: (install_token, event, total_tokens, received_at).
// That is the whole job — no other data arrives, nothing is sent back.
// Deploy with "Verify JWT" ON (nucleus sends the anon key — see phone_home.py).
import { createClient } from "npm:@supabase/supabase-js@2";

const admin = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return Response.json({ error: "POST only" }, { status: 405 });
  }
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch (_) {
    return Response.json({ error: "body must be JSON" }, { status: 400 });
  }

  // Validate exactly the contract — anything else is refused, not stored.
  const install_token =
    typeof body.install_token === "string" ? body.install_token.trim() : "";
  const event = body.event;
  const total_tokens = body.total_tokens;

  if (!install_token || install_token.length > 200) {
    return Response.json({ error: "install_token required" }, { status: 400 });
  }
  if (event !== "open" && event !== "close") {
    return Response.json(
      { error: "event must be 'open' or 'close'" },
      { status: 400 },
    );
  }
  if (typeof total_tokens !== "number" || !Number.isInteger(total_tokens) ||
      total_tokens < 0) {
    return Response.json(
      { error: "total_tokens must be a non-negative integer" },
      { status: 400 },
    );
  }

  const { error } = await admin
    .from("phone_home_events")
    .insert({ install_token, event, total_tokens });
  if (error) {
    console.error("phone-home insert failed:", error.message);
    return Response.json({ error: "could not store" }, { status: 500 });
  }
  return Response.json({ ok: true });
});
