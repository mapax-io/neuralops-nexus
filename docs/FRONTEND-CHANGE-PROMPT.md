# NeuralOps Nexus — the FRONTEND change prompt

**Document version: 0.1 (2026-10-15) — PARTIAL on purpose.** Everything the
BACKEND pins (contracts, endpoints, events, screens to build) is complete and
verified; §6 ("the repo itself") is a placeholder until the frontend
repository is cloned where the assistant can read it
(`/data/code/neuralops-react-app` on node3) — then this becomes 1.0 after a
verify-first read.

| Version | Date | What changed |
|---|---|---|
| 0.1 | 2026-10-15 | Backend-side half written at the close of Step 7; repo half pending the clone |

Give this file to the assistant at the start of any session that changes the
frontend. Its backend sibling is `docs/CHANGE-PROMPT.md` — same method, same
owner, same rules.

---

## 1. What the frontend is

The **hosted** NeuralOps web app (`neuralops-react-app`, React). It is NOT
self-hosted with the backend: one hosted app connects to ANY customer's
server by URL (a saved server list; `GET /auth/config/` previews a server's
version before connecting). Consequences that shape everything:

- **No cookies, no sessions** — every request carries
  `Authorization: Bearer <token>`: a Supabase JWT, or a LOCAL token from
  `/auth/local/signin/` (offline installs). The app treats both identically.
- **Every URL is server-relative** — media paths, API paths — resolved
  against the currently connected server (the app's absolutizeMedia pattern).
- **CORS is open on the server by design** (bearer tokens, not cookies) —
  never "fix" that.
- One user may connect to several servers over time; state is per-server.

## 2. The method (same as the backend's)

1. Settle each change in discussion; the owner rules.
2. **The contract lives in `docs/FRONTEND-REVAMP.md` BEFORE code** — if a
   screen needs a backend change, that lands backend-side first, recorded
   there, and this app builds against the recorded shape.
3. Verify-first: read the actual code (both repos) and quote file:line;
   never guess an endpoint — `docs/API.md` and the live
   `/api/v1/openapi.json` are the truth.
4. Build with tests where the repo has them; the owner verifies on the dev
   stack and the result is recorded.
5. Plain language everywhere — UI copy included. Backend errors
   (`{"detail": "..."}`) are WRITTEN to be shown verbatim; show them, don't
   rewrite them.

## 3. The sources of truth (read in this order)

1. `docs/FRONTEND-REVAMP.md` — THE work list: §1 the event/status contract,
   §2 the twelve screen items, §3 removals (terminal/browser panes, swarm).
2. `docs/API.md` — every endpoint with auth style, rights and error
   vocabulary.
3. `docs/CONCEPTS-AND-ROLES.md` — what the objects mean and who may do what;
   **gate every control on `GET /me/permissions/`** (resolved rights per
   object), never on a role name.
4. `docs/NUCLEUS-REVAMP.md` — why things are shaped this way (the rulings).

## 4. The realtime contract (Centrifugo)

The app subscribes per topic (channel `topic:{topic_id}`); the WebSocket
token/origin comes from the connected server. Event `type`s the app must
handle (shapes in FRONTEND-REVAMP §1 and chat/relay.py):

- **The reply lifecycle:** `message_start` → `message_delta` (tokens) →
  `message_done` (carries output_type, render_as, used_tools,
  retrieved_sources, embed_description, usage) · `message_error` ·
  `message_paused` (approval/question cards now pending — no message_done
  follows until resume).
- **Cards and steering:** `question_asked`, approval events, `nudge_taken`,
  `mention_refused` (why a persona will not answer, incl. code
  `reindexing`), `tool_activity` (the "using shell…" cue),
  `deep_escalation`, `context_retrieved` (the sources chip).
- **Ambient:** ordinary `message` (humans/system lines), `user_typing`,
  `usage_totals` (the topic's running cost — always "estimated"),
  `runbook_run` (a chain run's live state: status incl. `waiting`,
  current_step, step_results, checkpoint).

Message statuses on rows: pending / streaming / paused / completed / failed
/ stopped / cancelled. A paused bubble shows its cards; decisions go to the
REST endpoints and the stream resumes by itself.

## 5. The screens to build (the condensed work list — details in FRONTEND-REVAMP §2)

1. **Setup & login** (Step 4): fresh-install claim screen (show the CODE
   large, link to the portal, poll), the local/offline login form, the
   "Offline password" profile row + admin reset.
2. **Chat surfaces:** question/approval cards on paused replies; output-type
   rendering (render_as text/code/html/terminal); retrieved-sources chip;
   nudge "seen"/leftovers; stop; typing; refusal toasts with the backend's
   wording.
3. **Usage:** topic total in the status bar (live `usage_totals`), project
   and company rollups — every figure labeled "estimated — prices not
   confirmed".
4. **File viewer** (Step 5): browse/download/view with the exact error
   wording per status (404/400/409/413/415); render the view page in an
   `<iframe sandbox>`.
5. **Chains** (Step 7): definition editor (persona + checkpoint steps,
   supervisor, redo_limit), the run view (statuses incl. waiting, per-step
   results with verdicts/redos), the checkpoint answer box (403/409
   wording), the "cannot schedule a checkpoint chain" guard, the step-less
   birth template nudge ("add its steps first").
6. **Configure topic** (Step 6): nothing to gate client-side — just render
   it (it only appears for the four roles), ideally with a gear marker.
7. **Gateway tokens page:** mint (value shown ONCE with copy), list,
   revoke; the connection snippet (`/api/v1/mcp/` + Bearer).
8. **MCP servers:** stored tool list with read/write badges, Refresh button
   (502 detail verbatim), the zero-field OAuth **Connect** button (502
   detail verbatim), vendor presets only when their client_id is non-empty.
9. **Embedder setting + rebuild banner**; schedules UI; hooks UI; recall &
   deliverables; routines.
10. **Removals:** no terminal pane, no browser pane, no swarm UI.

OAuth popup pattern: open `authorize_url`, listen for the callback page's
`postMessage` `{type: "mcp-oauth-result", ok, server_id, error}` on the
window's origin.

## 6. The repo itself — TO FILL AT v1.0 (needs the clone)

To be written from a verify-first read of `neuralops-react-app` once it is
at `/data/code/neuralops-react-app`:

- Stack + pinned versions (React/TS/bundler/router/state/query libs, the
  Centrifugo client), node version, package manager.
- Project structure map (folders, one line each), the API client layer,
  where the server list / connection state / token live.
- The realtime layer (`lib/realtime/events.ts` is known to switch on the
  event `type` strings — a rename backend-side is a silent break).
- Component and styling conventions; how existing screens are composed.
- How to run it against the dev backend (ports 8096/3003, Tailscale
  Funnel), how to build, how to test; the owner's verify loop for UI work.
- The existing screens inventory vs. §5's to-build list — what is new, what
  is a change.

**Until then:** sessions may design against §1–§5 but must not guess the
repo's internals.
