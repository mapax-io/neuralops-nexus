# NeuralOps portal — the claim-code pieces (deploy guide)

What this folder is: the portal half of the install-claim flow. The server
half (nucleus's setup screen + setup/start + setup/poll) is already built and
tested (Step 4). These four pieces make the portal answer it for real.

**The flow in one breath:** fresh install asks `device-request` for a code →
shows it on its own screen → the person signs in on the claim page and types
the code → `device-claim` records who typed it → the install's polling of
`device-poll` receives that person's token ONCE → the install verifies it and
makes them the owner.

**Where the page lives (changed 2026-10-18):** Supabase refuses to serve web
pages from edge functions — its gateway rewrites every function response to
`text/plain` + a sandbox policy (anti-phishing rule on *.supabase.co), so a
browser shows raw HTML text. The claim page is therefore a STATIC file,
`portal/claim-page/index.html`, hosted anywhere (for testing:
`cd portal/claim-page && python3 -m http.server 8899` → open
`http://<that machine>:8899`; later the real portal domain). It holds only
the public publishable key. The old `functions/claim-page/` edge function is
retired — delete it from the dashboard if deployed.

**The security ruling (owner, 2026-10-18):** only the person at the install's
screen can ever claim it. The code exists only on that screen; the request id
is unguessable and only the install holds it; the token is handed out exactly
once; the portal can never push anything into any server; a claimed install
refuses all further claims (409, tested). `manage.py create_owner` stays the
shell-only air-gapped fallback.

## Deploy — four steps in the Supabase dashboard

1. **The table.** SQL Editor → New query → paste `schema.sql` → Run.
2. **Four functions with JWT verification ON** (the default):
   Edge Functions → Deploy new function → name it EXACTLY as the folder —
   `device-request`, then `device-poll`, then `device-claim`, then
   `phone-home` — pasting each folder's `index.ts`. The names are nucleus's contract (core/settings.py
   defaults point at `/functions/v1/device-request` and `/device-poll`).
   Note: the editor's Save is NOT Deploy — the live function only changes
   when the Deploy button is pressed.
3. **The page**: host `portal/claim-page/index.html` (see "Where the page
   lives" above) — it is NOT an edge function.
4. **Auth settings** (Authentication → Sign In / Up): email+password enabled.
   If "Confirm email" is ON, a new sign-up must click the email link before
   signing in — fine for production; for quick testing you may turn it off.
5. **Nothing to configure in nucleus** — its defaults already point at this
   project's function URLs.

## Test it

**A — functions alone (any terminal):**

```bash
# ask for a code, like an install would (anon key required, same as nucleus sends)
curl -s https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/device-request \
  -H "Authorization: Bearer <ANON_KEY>" -H "Content-Type: application/json" \
  -d '{"server_url":"https://test.example"}'
# → {"code":"483-291","request_id":"<uuid>","expires_in":900}

# poll it — pending until someone types the code on the page
curl -s https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/device-poll \
  -H "Authorization: Bearer <ANON_KEY>" -H "Content-Type: application/json" \
  -d '{"request_id":"<uuid from above>"}'
# → {"status":"pending"}
```

Open the hosted claim page in a browser, sign up/in, type the code — the
next poll returns `{"status":"claimed","access_token":"..."}` once, then
`{"status":"denied"}`. Polling with the CODE instead of the request_id is
refused (denied) — by design.

Test A ran green against the live project on 2026-10-18 (see
docs/NUCLEUS-REVAMP.md).

**C — phone-home (any terminal):**

```bash
# a report, exactly as nucleus sends it (core/phone_home.py)
curl -s https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/phone-home \
  -H "Authorization: Bearer <ANON_KEY>" -H "Content-Type: application/json" \
  -d '{"install_token":"test-install-1","event":"open","total_tokens":1234}'
# → {"ok":true}

# garbage is refused, not stored
curl -s https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/phone-home \
  -H "Authorization: Bearer <ANON_KEY>" -H "Content-Type: application/json" \
  -d '{"install_token":"test-install-1","event":"reboot","total_tokens":-5}'
# → {"error":"event must be 'open' or 'close'"}
```

Then Dashboard → Table Editor → `phone_home_events` should show the one row.
Delete the test row after checking.

**B — the real thing (dev stack):** with a fresh install (no users), open the
app's setup screen → it shows a code → claim it on the page → the setup
screen finishes with you as owner. The second claim attempt answers 409.

## Files

| File | What | JWT verify |
|---|---|---|
| `schema.sql` | the `device_requests` table, RLS locked (service-role only) | — |
| `functions/device-request/` | install asks for a code | ON |
| `functions/device-poll/` | install polls; token handed out once | ON |
| `functions/device-claim/` | the page claims with the person's session | ON |
| `functions/phone-home/` | installs report their one token total (open/close) | ON |
| `../claim-page/index.html` | the browser page (sign in + type the code) — static, hosted anywhere | — |
| `functions/claim-page/` | RETIRED — Supabase won't render HTML from functions; kept for history | — |
