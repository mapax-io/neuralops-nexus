# NeuralOps Frontend — Revamp

**Started:** 2026-10-14. Plain language on purpose (owner's rule).
**The app:** the `neuralops-nexus-web-app` repo (its own repository, not a
module of this one). Hosted frontend (Vercel → neuralopsnexus.ai) + many
self-hosted servers; dev runs on localhost:3000.
**The rule:** the event/status contract below is the single source of truth
between nucleus and the frontend. Any change lands HERE first, then in code —
the frontend never discovers a new event at runtime.

**Companions:** `docs/NUCLEUS-REVAMP.md` (the steps), `docs/NUCLEUS-HANDOFF.md`
(changes 1–14), `docs/NEXUS-AI-REVAMP.md` (the engine, done).

---

## 1. The live contract — what the relay sends to the screen

Events (over Centrifugo, per topic channel). The engine already emits all of
these (verified by its 106 tests); nucleus's new relay (Step 2) passes them on.

| Event | What the screen does |
|---|---|
| `message_start` | show the reply bubble, spinner on |
| `message_delta` | append streamed text |
| `keepalive` | nothing (keeps the connection judged alive) |
| `tool_call_start` / `tool_call_end` | the activity trail row (name, ok, duration, preview, url) |
| `approval_requested` | the APPROVAL card (tool, args preview, allow/deny, "always allow" for unlabeled reads) |
| `question_asked` | NEW — the QUESTION card: question + option buttons + free-text; answer goes back on the resume road |
| `message_paused` | reply parks (status PAUSED); its pending cards were already published (tool_approval / question_asked). Deciding ALL of them resumes the run — new deltas then arrive on the SAME message id, no new bubble |
| `deep_escalation` | small "handed to <model>" note |
| `context_retrieved` | NEW — "searched project memory, used N items" chip; references are linkable ids |
| `nudge_taken` | NEW — mark the user's typed nudge as "seen by the persona" |
| `message_done` | final content; render by `render_as`; store `output_type`; show `answered_by_model`, usage numbers, `used_tools`, `retrieved_sources` |
| `message_error` | the error bubble |
| `tool_approval` / `tool_approval_decided` | the approval card appears / shows its verdict (nucleus-side events, kept from 0.8.0) |
| `question_answered` | NEW (Step 2) — the question card shows its answer; the run resumes by itself once every pending card is decided |
| `tool_activity` / `tool_activity_end` | the activity trail rows (nucleus-side names for the engine's tool_call events, kept) |
| `usage_totals` | NEW (Step 1) — the topic's running spend, pushed by nucleus after every usage insert: `{topic_id, input_tokens, output_tokens, cost (string or null), unpriced_rows, price_estimated: true}`. Show it in the topic's status bar; money ALWAYS carries the label "Estimated — prices not confirmed" (owner's ruling); `unpriced_rows > 0` means "at least this much" |

Message rows now carry: `output_type`, `render_as`, `embed_description`,
`used_tools`, `retrieved_sources`, and a real `status`
(PENDING/STREAMING/COMPLETED/FAILED/CANCELLED/PAUSED). A broken typed reply
arrives ALREADY downgraded to text — the frontend never trust-parses content.

Output renderers (ten types, same as 0.8.0): text, html, chart, table,
diagram, form, terminal, code, preflight, choice.

## 2. New screens and cards this revamp needs

1. **Question card** (engine item 5) — options are suggestions, free text
   always allowed; only the person who started the run answers; read-only for
   others; expires like approvals.
2. **Preflight plan card** — the plan reply (output_type=preflight) with
   Approve / Reject; an approved plan re-triggers with `approved_plan`.
3. **Usage everywhere** (Step 1 — nucleus half BUILT) — topic totals in the
   status bar (live from `usage_totals`, plus GET
   `/projects/{p}/channels/{c}/topics/{t}/usage/` on open — visible to anyone
   in the topic); the project spend page (GET `/projects/{p}/usage/`, needs
   usage.view_project — per-persona and per-model splits); the company spend
   page (GET `/usage/company/`, needs usage.view_company — per-project and
   per-model). Every response carries `price_estimated: true` and the note
   "Estimated — prices not confirmed" — the UI shows the label verbatim.
   Delegation rows ({msg}:cpN) appear under the CALLEE persona.
4. **File viewer** (Step 5 — nucleus half BUILT) — the project's folder on
   the server. Browse: GET `/projects/{id}/files/?path=` → `{path,
   entries: [{name, type: dir|file, size, modified}], truncated}` (folders
   first, then by name; `size` null for folders). Download: GET
   `/projects/{id}/files/content/?path=` — a streamed attachment, any size.
   View: same URL `&as=html` — one self-contained page (markdown rendered,
   code highlighted, images shown); it arrives with
   `Content-Security-Policy: sandbox`, and the app should ALSO render it in
   an `<iframe sandbox>` — belt and braces, since project files are written
   by personas. Errors to word in the UI: 404 no such file · 400 bad path or
   dir/file mixed up · 409 the project has no folder yet · 413 too big to
   view (offer the download) · 415 binary (offer the download). Later: git
   diff, edit, select-a-portion-to-chat.
5. **Chain / workflow screens** (Step 7 — nucleus half BUILT). Chains ARE
   runbooks; same endpoints, new powers:
   - **Definition:** `RunbookIn/Out` gained `supervisor_id`/`supervisor_name`
     (one optional reviewing persona), `redo_limit` (0–2), `has_checkpoint`,
     and steps gained `kind` ("persona" | "checkpoint") — a checkpoint step is
     `{kind: "checkpoint", question, on_failure: stop|skip}`. Patch clears the
     supervisor with `clear_supervisor: true`.
   - **Watching a run:** `RunbookRunOut.status` adds `waiting`;
     `checkpoint: {index, question, asked_at}` is set while waiting — show the
     question as a banner/card in the topic. Step results now carry `redos`
     and `verdict` (approve | redo | fail | unclear | unreviewed) when a
     supervisor reviewed, and checkpoint entries
     `{kind: "checkpoint", status: answered|expired, question, answer,
     answered_by}`. Verdicts are ordinary persona messages in the topic —
     nothing extra to render there.
   - **Answering:** POST `…/runbooks/runs/{run_id}/checkpoint/` `{answer}` —
     200 continues the run; 403 = only the starter or a project admin may
     answer; 409 = not waiting (someone else answered, or it expired). A
     checkpoint expires after 24h (like question cards) — the run then skips
     or fails per the step's on_failure.
   - **Scheduling guard:** a chain with `has_checkpoint: true` cannot be
     scheduled — the 400's detail says "run it by hand"; grey the option out.
     A chain with no steps (the birth template "Draft and review") cannot run
     until edited — 400 "add its steps first".
6. **The "configure" topic** (Step 6 — nucleus half BUILT) — every project
   now carries a topic titled "configure" (in its general channel,
   `is_configure: true` — but the flag never reaches the API; the topic
   simply APPEARS in lists for company/project owner+admins and doesn't for
   anyone else, enforced server-side on every road). Frontend: nothing to
   gate — just render it, ideally with a small gear marker; the provisioning
   persona will live there (MCP track).
7. **Connector toggles + the gateway's token page** (Step 6):
   - Toggles ship WITH the bundled connectors (MCP track) — scope ruling: no
     dead switches for services that don't run yet.
   - **Gateway tokens page (nucleus BUILT):** POST `/gateway/tokens/`
     `{name, user_id?}` → the token value appears ONCE in the response
     (`token: "nxg_…"`) — show it with a copy button and say it won't be
     shown again. GET lists `{id, name, user_id, user_email, created_at,
     last_used_at}` (admins see everyone's); DELETE `/gateway/tokens/{id}/`
     revokes. Only the four roles may create (403 otherwise); company-level
     admins may create FOR a member (user_id). Connection snippet to show:
     MCP endpoint = `<server>/api/v1/mcp/`, header
     `Authorization: Bearer nxg_…`.
   - **MCP server screen:** `MCPServerOut.tools` now carries the stored tool
     list `[{name, description, read_only}]` — render one line per tool with
     a read/write badge (read_only null = write). A "Refresh tools" button →
     POST `/mcp-servers/{id}/tools/refresh/` → 200 `{tools}` or 502 whose
     detail is shown verbatim next to the button.
   - **The Connect button (Step 6 Part C, nucleus BUILT):** for an oauth2
     server the user now fills in ZERO OAuth fields by default — just the
     server URL. GET `/mcp-servers/{id}/oauth/authorize/?frontend_origin=` →
     200 `{authorize_url}` (open it in the popup; the self-closing callback
     page posts `mcp-oauth-result` back, unchanged) or **502 whose detail is
     shown verbatim** next to Connect — it already tells the admin what to do
     (usually: this provider has no self-registration, paste your own app's
     client_id). The paste-your-own fields stay, as the "advanced" fallback.
   - **Catalog presets:** `MCPCatalogEntryOut.oauth_preset` (github /
     atlassian / google-drive only) — when present AND its `client_id` is
     non-empty, offer "Connect with NeuralOps" (copy the preset into
     oauth_config on create); while `client_id` is empty (vendor apps not yet
     registered), show only the ordinary roads. Never render any secret
     field from a preset — there is none.
8. **Login changes** (Step 4 — nucleus half BUILT). Three pieces:
   - **Setup (fresh install) — RULING (owner, 2026-10-18 evening,
     SUPERSEDES the setup-screen design above and the earlier same-day
     one-click ruling):** the app never offers setup or a claim. Ownership
     starts ONLY from the server's own terminal — `manage.py create_owner`
     shows the code + portal link, the person claims at the portal page, the
     command creates the owner. The web roads /auth/setup/start|poll/ are
     REMOVED from nucleus (a public start/poll let anyone on the network
     race the real owner for a fresh install). The app's whole job: when a
     connect finds an unowned server, show the plain message "this server
     isn't set up yet — whoever installed it needs to run the setup command
     (create_owner) in its terminal" (already in src/app/servers/page.tsx).
     GET /auth/setup/status/ still exists (needs_owner, local_login_enabled,
     portal_url) if the app ever wants a finer message. The withdrawn dialog
     lives in the app repo's _attic/ as raw material.
     Local (offline) login UI: PARKED (owner, 2026-10-18) — Supabase login
     stays the only road in the UI for now; the backend endpoints exist and
     wait.
   - **Local (offline) login form:** POST `/auth/local/signin/`
     `{email, password}` → `{access_token, token_type, expires_hours, user}`.
     The token goes in the same Authorization: Bearer header as a Supabase
     one — every endpoint accepts either. 401 = wrong email or password (one
     message on purpose); 403 = local login turned off on this server
     (hide the form when setup/status says `local_login_enabled: false`);
     429 = too many tries, say "wait a few minutes".
   - **Profile row "Offline password":** POST `/auth/local/set-password/`
     `{password}` (400 carries Django's validator reasons — show them).
     Admin side, on a member's row: POST `/auth/local/reset-password/`
     `{user_id, password}` — needs the company.local_password right (Owner/
     Admin); hide the control when `/me/permissions/` lacks it.
9. **Nudge polish** — typed-while-running messages show "seen" when
   nudge_taken arrives; leftovers appear as ordinary messages after the reply.
10. **Retrieved-sources chip** — on any reply that used project memory, list
    the references (document / earlier message / recall / tool memory with its
    date label).
11. **Embedder setting + rebuild banner** (Step 3 — nucleus half BUILT) — a
    project settings row: the embedder spec (GET/PUT
    `/projects/{id}/embedder/`; PUT needs the company owner/admin — the
    server enforces it, the UI hides the control otherwise). While
    `reindex_status` is "building", show a project-wide banner ("memory is
    being rebuilt") — persona mentions come back refused with code
    `reindexing` meanwhile; "failed" shows a retry hint (re-save the setting).
12. **Question card POST path** (Step 3): the answer goes to POST
    `…/messages/{id}/questions/{call_id}/` with `{text}`; the reply resumes
    by itself when every pending card is decided. An expired card (24h)
    arrives as a deny / "(no answer …)" decision made by "expiry".

## 2b. Built so far (frontend side)

**BUILT (2026-10-18) — the /add_code claim page (the portal page moves INTO
this app).** `src/app/add_code/page.tsx` + `src/lib/api/claim.ts`: signed in
→ code box (auto-formats 483291 → 483-291) → claims via the portal's
device-claim function with the person's own session; signed out → the
LoginForm renders ON the page itself (new nextPath prop — default /servers,
/add_code passes itself), so sign-in/sign-up happens without leaving, and
the code box appears the moment the session exists; after a successful
claim the page moves to /servers by itself (owner's sequencing ruling).
create_owner's printed link points here:
image default `https://neuralopsnexus.ai/add_code` (neuralops/Dockerfile),
dev override `http://192.168.1.90:3000/add_code` (compose nucleus-dev's
NEURALOPS_PORTAL_URL — rebuild not needed, restart is). The static
`portal/claim-page/index.html` stays as the no-app fallback.
VERIFY (owner): with the web app running — create_owner in the server's
terminal → open the printed link → page shows the code box → type the code
→ "Done!" → the terminal finishes with you as owner.

**BUILT then WITHDRAWN (2026-10-18) — chunk 1, the in-app setup dialog.**
Built as a setup/claim dialog on the servers screen (one-click claim with
the signed-in account), then withdrawn the same evening by the terminal-only
ruling (§2.8 above): an in-app claim would let anyone who can reach a fresh
install race the real owner. What remains in the app: the "not set up"
connect outcome shows the run-the-setup-command message. The withdrawn files
sit in the app repo's `_attic/` with a README. Chunk 1's VERIFY is now the
backend's (NUCLEUS-REVAMP: create_owner code flow + closed web roads + the
app connecting the new owner straight into the workspace — that last step is
still this app's test, and still closes end-to-end test B).

## 3. Removals

Terminal pane and browser pane screens (items 41/42, dropped), and any UI for
the swarm road. Message search stays (nucleus keeps it as plain DB search).

## 4. Order

The frontend follows nucleus's steps: each nucleus step that changes the
contract updates §1 here first, then the matching screens ship with that step.
