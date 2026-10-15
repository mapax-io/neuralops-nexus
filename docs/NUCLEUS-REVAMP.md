# NeuralOps Nucleus — Revamp

**Started:** 2026-10-14. **Owner rulings recorded the same day.**
**Written in plain language on purpose** (owner's rule).
**Method:** same as the nexus-ai rebuild — audit first (read the code, quote
file:line, never guess) → settle each area in discussion → write it here →
build with acceptance tests.

**Companion documents:**
- `docs/NUCLEUS-HANDOFF.md` — changes 1–14: everything the finished nexus-ai
  engine needs from nucleus. That file is the detailed work list; this file is
  the architecture plan around it.
- `docs/NEXUS-AI-REVAMP.md` — the engine rebuild (done: Layers 0–6, 106 tests).

---

## 1. What nucleus does today (verified inventory, read 2026-10-14)

| Area | Where | What it is |
|---|---|---|
| Login & accounts | `authn/`, `nucleus/models/governance.py` | Sign-in through Supabase (JWT), User, Company, invitations, avatars |
| Permissions | `authn/permissions/` | The rights registry (~40 actions), 4 roles, PermissionChecker — **good, keep** |
| Workspace | `workspace/api.py` (496 lines) | Projects, channels, topics, team members, deliverables — plus dead terminal/browser endpoints |
| Chat | `chat/` — `services.py` is **1,777 lines** | Save messages, @mentions, trigger nexus-ai, relay its stream to the screen, approvals, nudges, stop, search |
| AI config | `intelligence/api.py` (759 lines) | Models (+check button, encrypted keys), personas, MCP servers (+OAuth), routines, recall |
| Context | `context/` | File/web sources per topic, media storage, embed calls to nexus-ai |
| Scheduling | `scheduling/` | Schedules (celery-beat), runbooks + runs, inbound hooks (public token URL) |
| Internal API | `internal/api.py` | Everything nexus-ai calls back: personas, history, approvals, nudges, recall |
| Infra | `core/settings.py` | Celery+Redis, Centrifugo, Supabase, Django admin |
| Maybe-dead tables | `nucleus/models/extended.py` | KnowledgeBase/File/Chunk, EmbeddingJob, VectorDocument, Upload/UploadPart, AuditEvent, Notification, SavedSearch, SearchLog — **liveness NOT yet verified** |

---

## 2. The revamp areas (owner rulings 2026-10-14)

### 2.1 Login (SETTLED: option B, plus the code flow)
- Supabase stays the default — it is the identity/license anchor.
- **Add a local fallback** so a customer can still log in when Supabase (or
  the internet) is not reachable: local accounts / OIDC option for air-gapped
  installs. "Nothing leaves your network" must include login.
- **Owner setup becomes a code flow (owner, 2026-10-14):** instead of the
  `create_owner` management command, the owner signs in on OUR portal page
  online, gets a short code, and types that code into their fresh install —
  the install claims itself. Replaces shell access with a 30-second step.
  (Planned for this revamp; design when the authn area is opened.)

### 2.2 The chat monolith (SETTLED: split and rewrite)
`chat/services.py` (1,777 lines) splits into parts with one job each:
message saving/parsing · sessions · approvals+preflight · nudges · the
trigger road. Old garbage goes. Rewritten against the new event vocabulary
(handoff changes 2, 8, 9, 11).

### 2.3 The relay and the nexus-ai client (SETTLED: own components)
- **The relay** — the loop that reads nexus-ai's stream, publishes to
  Centrifugo and updates message rows — becomes its own designed component
  with its own tests. Queue-per-topic (one reply at a time per topic) lives
  here. Chain checkpoints (Layer 6) and pause expiry hang off it.
- **A clean `NexusAIClient` in nucleus** (owner: "there must be some client
  here for nexus-ai"): today the calls to nexus-ai are scattered httpx code
  inside services. One client class holds every call — trigger, embed,
  reindex, model check — mirroring how the engine has one `NucleusClient`
  for the other direction. One place for the internal key, timeouts, errors.

### 2.4 The money tables (SETTLED: build them)
New schema: a usage row per model call (all fields the engine already sends —
tokens, cache, cost as Decimal, kind: chat_reply/router/memory/embedder),
summed per topic/project/persona/company. Powers: the usage endpoint
(change 1), topic totals in the status bar (47), budgets (14), rate limits
(10/11), and the phone-home total (change 13.6). Biggest new piece.

### 2.5 Dead and duplicate code (SETTLED: remove all of it)
Owner's ruling: remove everything that is dead or duplicated — after the
audit proves each one has no live writers/readers. The kill list so far:
`chat/tasks.py` (nucleus calling AI models itself), the swarm road, the
terminal/browser endpoints + their settings, and the `extended.py` tables
that duplicate the Layer 3 vector DB (KnowledgeChunk, EmbeddingJob,
VectorDocument) or collide with item 36 (Upload/UploadPart vs MinIO).
Each removal is recorded here with the proof it was dead.

### 2.6 Scheduling trio (SETTLED: one clear job each)
- **Schedule** = WHEN something fires (celery-beat rows). Item 29's home.
- **Runbook** = a saved CHAIN definition (Layer 6: team + stages + criteria).
- **Routine** = a saved per-turn preset (prompt/tool shaping via `/name`).
No overlaps; anything not fitting one of these three gets merged or removed.

### 2.7 Production posture (SETTLED: fix)
DEBUG off by default, SECRET_KEY generated per install (it belongs in
secrets.env beside the other five), real ALLOWED_HOSTS, CORS locked to the
app origin, media served by nginx not Django.

### 2.8 Durable approvals (SETTLED: rows, not cache)
Approval and question decisions become permanent rows (who decided what,
when) instead of Redis entries with a TTL. The provisioning MCP's audit
requirement (§4.5 of the engine doc) is answered by the same table.

### 2.9 The new front doors (already settled in the handoff)
The NeuralOps MCP gateway (per-user tokens, change 13) and the workflow MCP's
chain state (change 14) — nucleus schema + API work, specified in the handoff.

### 2.10 The frontend contract (SETTLED: versioned deliberately)
Every new event/status (question cards, output types, retrieved sources,
nudge taken) is one documented contract with `neuralops-react-app`, updated
in lockstep, not discovered by the frontend at runtime.

---

## 3. NEW FEATURE — the project file viewer (owner, 2026-10-14)

**What:** every project gets a file browser over its default folder (the same
`/nexus/projects/<slug>` folder the personas' filesystem tools write into).

**v1 (this revamp):**
- Browse the folder tree.
- **Download any file.**
- **View as HTML** in the browser: markdown rendered, code shown highlighted,
  text/images shown directly; anything else is download-only.
- Safety: paths are locked inside the project folder (no `..`, no symlinks
  out), a size cap on rendered views, `project.view` permission required.
- API sketch: `GET /projects/{id}/files/?path=` (list),
  `GET /projects/{id}/files/content/?path=` (download),
  `...&as=html` (rendered view).
- To verify in the audit: nucleus's container mounts the projects volume the
  same way nexus-ai's does (compose shows one shared volume — confirm).

**Later (recorded now, built later):**
- Git diff view of the folder (what the personas changed).
- View, EDIT, or SELECT a portion of a file and send it to chat.

---

## 4. THE STEPS (settled 2026-10-14) — like the engine's layers, in order

Each step: settle its details here → build → acceptance tests → owner
verifies → next step. One step at a time, never two half-done.

### Step 0 — Audit and kill list
Prove what is dead, then delete it (ruling 2.5). For each extended.py table:
find its writers and readers (git grep, quote file:line) → record the verdict
here → drop the dead ones in one migration. Same for chat/tasks.py, the swarm
road, terminal/browser endpoints. Also verify: nucleus's container mounts the
projects volume (needed for Step 5).
**Done when:** every removal is recorded with proof; the stack boots; chat
still works end to end.

**AUDIT RESULTS (run 2026-10-14; every count = grep of all nucleus .py files,
excluding each model's own definition file and admin):**

| Candidate | References | Verdict |
|---|---|---|
| KnowledgeBase / KnowledgeFile / KnowledgeChunk | 0 (one docstring mention) | **DELETED** (migration 0029) |
| EmbeddingJob / VectorDocument | 0 | **DELETED** — duplicated the Layer 3 vector DB |
| Upload / UploadPart | 0 | **DELETED** — item 36 (MinIO) replaces the idea |
| ProjectContext | 0 | **DELETED** (TopicContext is the live one — kept) |
| AuditEvent | 0 (one docstring mention) | **DELETED** — Step 3 designs the durable-approvals table fresh |
| Notification / UserSession / SavedSearch / SearchLog | 0 each | **DELETED** |
| ChatReaction / ChatAttachment | 0 each | **DELETED** |
| TopicContext | 4 (internal/api.py:416–418 serves it) | ALIVE — kept |
| AIRequestLog | writer internal/api.py:451, reader intelligence/api.py:636 | ALIVE but orphaned — the current engine never calls its endpoint; **Step 1 replaces it** with the money tables |
| Prompt / PromptTemplate | intelligence/services.py:597,654 | ALIVE — kept |
| Deliverable, ChatSession, ChatReadMarker, Routine, RecallEntry, Runbook, RunbookRun, InboundHook, PersonaSchedule | 5–37 each | ALIVE — kept |
| chat/tasks.py (nucleus calling AI models itself) | ZERO callers of generate_ai_response, zero imports of chat.tasks | **RETIRED** → moved to `.step0-removed/chat_tasks.py` (delete the folder when happy) |
| Swarm road (services.py trigger_ai_swarm_response_async + /trigger/swarm/) | LIVE — called from chat/api.py:323–402 against the LEGACY engine | NOT deleted now; **dies in Step 2** (the new engine has no swarm endpoint) |
| Terminal/browser endpoints (workspace/api.py:141,160) | reachable; panes dropped by decision (items 41/42) | NOT deleted now; **removed in Step 2** together with the frontend panes |
| ChromaDB services + CHROMA_* env (compose) | used by the LEGACY engine only | removed at **switch-over (Step 8)** |

**Executed 2026-10-14:** 15 models removed from `nucleus/models/workspace.py`
+ `extended.py` + `__init__.py`; migration **0029_step0_kill_list** drops the
tables (FK dependents first); `chat/tasks.py` retired; two stale docstrings
cleaned (base.py, permissions/models.py). **Volume check for Step 5: PASSED**
— the compose file mounts `./projects:/nexus/projects` on nucleus AND
nexus-ai in both profiles (the file viewer can be served by nucleus).

**VERIFIED (owner, 2026-10-14):** migration 0029 applied cleanly on the dev
stack (`Applying nucleus.0029_step0_kill_list... OK`). The dev database was
also eleven migrations behind — 0018–0028 applied in the same run, so the
Routine/Runbook/Deliverable tables newer code expected now exist. Note for
`docker exec` into the unified image: the `nucleus-env` wrapper is an
ENTRYPOINT mode, not a binary — exec with the venv directly:
`docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus
neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py …`.
**STEP 0 CLOSED** — chat smoke rides daily use; any breakage traces to
exactly fifteen zero-reference tables and one caller-less file.

### Step 1 — The money tables (handoff change 1 + item 47)
The usage schema, the `POST /internal/usage/` endpoint receiving the engine's
real records (chat_reply / router / memory / remote_embedder), cost as
Decimal, totals per topic/project/persona/company, topic totals pushed to the
status bar.
**Done when:** a real reply's tokens land as rows and the topic total updates
live; the engine's records are accepted unchanged.

**Step 1 rulings (owner, 2026-10-14):**
1. **Prices come from an online price API, auto-updated** — a periodic job
   refreshes a local price catalog; the admin can still override the three
   numbers (input / cached / output per million) on any model config; local
   models stay 0. **Every money figure in the UI carries the label:
   "estimated — prices not confirmed."** Offline installs: the fetch fails
   silently, the last-known catalog (or the admin's numbers) keeps working.
2. **Visibility:** members see topic totals where they participate; project
   admins see project totals per persona; company owner/admin sees
   everything. (Two new rights: usage.view_project, usage.view_company.)
3. **Retention:** keep every detailed row, no pruning in v1.

**Design notes (settled at build):** usage rows carry NO foreign keys — plain
indexed id columns — because billing records must survive any deletion, and
the engine's delegation rows use composite message ids ("msg:cp0") that are
not FK-able. Cost is Decimal, computed at insert from (admin override →
catalog → none = cost null, still counted in tokens).

**Built 2026-10-14 — what landed where:**

| Piece | File | What it does |
|---|---|---|
| The two tables | `nucleus/models/usage.py` | `UsageRecord` (one row per model call, engine field names kept byte for byte) + `ModelPrice` (the local price catalog) |
| Admin override | `nucleus/models/intelligence.py` | three new columns on ModelConfig: `price_input/cached/output_per_million` — blank = use the catalog |
| Migration | `nucleus/migrations/0030_money_tables.py` | creates both tables + the three override columns |
| The math | `intelligence/pricing.py` | override → catalog → nothing; exact Decimal; cache writes priced at the input rate (an estimate — the label says so); never raises |
| Price refresh | `intelligence/tasks.py` | `refresh_model_prices` — daily Celery beat task, fetches `MODEL_PRICES_URL` (default: LiteLLM's public catalog on GitHub), fails SILENTLY offline (last-known prices keep working) |
| Settings | `core/settings.py` | `MODEL_PRICES_URL` (empty = refresh off) + the beat schedule entry |
| Write endpoint | `internal/api.py` | `POST /api/v1/internal/usage/` — the engine's batch → priced rows → `usage_totals` pushed on each affected topic's channel |
| Read endpoints | `intelligence/usage_api.py` | topic totals (anyone in the topic), project rollup (usage.view_project), company rollup (usage.view_company) — every response says `price_estimated: true` + "Estimated — prices not confirmed." |
| Mounts | `core/urls.py` | `/projects/…/usage/` + `/usage/company/` |
| Rights | `authn/permissions/rights.py` | `usage.view_project`, `usage.view_company` — Owner + Admin bundles (needs `manage.py seed_permissions` once) |
| Tests | `intelligence/tests_usage.py` | 11 tests: the pricing order and exact math, the endpoint (401 / priced rows / cost-null / live totals), the three gates |

The frontend's half (the `usage_totals` event + the three GET windows) is
recorded in `docs/FRONTEND-REVAMP.md` §1 and §2.3.

**VERIFIED (owner, 2026-10-14):** migration 0030 applied cleanly
(`Applying nucleus.0030_money_tables... OK`); `seed_permissions` reported
46 rights in the registry, 12 newly created; the test suite ran on the dev
stack: **11 passed, 0 failed** — and the run pushed REAL `usage_totals`
events through the dev Centrifugo (`POST centrifugo-dev:8000/api/publish
200 OK`), so the live push is proven, not mocked. Two bugs the first run
caught and the fix kept: (a) aggregate aliases must not reuse column names
(`cost=Sum("cost")` made the `cost__isnull` filter hit the aggregate —
FieldError); (b) the 6-dp price column returns `"2.500000"`, so price
strings compare as Decimals. **STEP 1 CLOSED.** The last "done when" piece
— a real reply's tokens landing as rows — arrives free at switch-over
(Step 8), when NEXUS_AI_URL points at the new engine; the endpoint already
accepts the engine's records verbatim (the schema mirrors its dataclass).

### Step 2 — NexusAIClient + the relay + chat split
One client class for every call to nexus-ai; the relay as its own component
(new events, message statuses, queue-per-topic, pause storage); services.py
split into small modules; garbage deleted.
**Done when:** every engine event type relays correctly (the engine's 106
tests define the contract) and two triggers on one topic run in order.

**Step 2 rulings (owner, 2026-10-14):** 1. the 300-line swarm relay, the
/swarm directive and its events are DELETED (the new engine has no swarm
endpoint); 2. approvals switch from polling to the engine's pause-and-resume
(there is no polling to keep); 3. @session stays as-is; 4. the client is
`NexusAIClient` in `chat/nexus_ai.py`.

**The split (services.py 1774 lines → six small files):**

| New file | What moves there |
|---|---|
| `chat/directives.py` | @mention/@session/@output-type//routine parsing, `MessageDirectives` |
| `chat/realtime.py` | `publish`, `publish_async`, `topic_channel` |
| `chat/messages.py` | create/update/fail AI message, save user/system message, list, serialise, orphan reaper, stop/nudge checks, sessions |
| `chat/approvals.py` | preflight plans + tool approvals (claim/decide), rewired to fire a RESUME instead of feeding a poll |
| `chat/nexus_ai.py` | **NexusAIClient** — trigger (SSE), resume (same endpoint + ResumeBlock), embed; the only file that knows NEXUS_AI_URL |
| `chat/relay.py` | the relay — one reply's whole life, queue-per-topic |
| `chat/services.py` | thin re-export shim so other apps' imports keep working |

**Pause-and-resume (contract verified in the engine's code, 2026-10-14 —
nucleus_client.py:83, specs.py:121–141):** the engine POSTs
`POST /internal/messages/{msg_id}/pause/` — `{job_id, topic_id, persona_id,
state, catalog_hash, pending:[{call_id, tool, capability_id, args_preview,
kind: approval|question}], role}` — BEFORE `message_paused` ends the stream.
Nucleus stores it in a new `PausedRun` table (migration 0031; the state JSON
is too big for message metadata and must never ride to the browser). A
decision re-sends the ORIGINAL trigger job (also stored on the PausedRun row)
plus `resume: {state, approvals, answers, role}`. The old internal approvals
poll GET is deleted. Question ANSWER endpoint + cards stay Step 3; the relay
already stores pending questions here.

**Also in this step:** message statuses grow STREAMING / PAUSED / CANCELLED
(same migration); `message_done` now stores `loaded_tools`, `used_tools`,
`retrieved_sources`, `embed_description` on the row; new events relayed:
`question_asked`, `message_paused`, `deep_escalation`, `context_retrieved`,
`keepalive` (eaten, never relayed to the browser).

**Built 2026-10-14 — what landed where:**

| Piece | File | Notes |
|---|---|---|
| The split | `chat/directives.py`, `chat/realtime.py`, `chat/messages.py`, `chat/approvals.py` | moved from services.py; /swarm directive deleted; serialise adds `questions`, `used_tools`, `retrieved_sources` |
| The client | `chat/nexus_ai.py` | `NexusAIClient.stream_trigger()` (SSE + Stop support) and `.embed_message()` — the only file that knows NEXUS_AI_URL |
| The relay | `chat/relay.py` | all 13 event types; queue-per-topic (`_topic_locks`); PENDING→STREAMING→terminal; pause parks (status PAUSED + job onto PausedRun); `resume_paused_run()`; the job now sends company_id/project_id/user_id (O2 — Step 1's usage rows get real ids) |
| The shim | `chat/services.py` | re-exports everything; swarm relay (300 lines) and `approval_state` (the poll) DELETED |
| Pause storage | `nucleus/models/runtime.py` + migration `0031_paused_runs.py` | `chat_paused_run` table + PAUSED status; the resume fires only when EVERY pending call is decided (the engine needs a result per deferred call — reply_generator.py:_deferred_results) |
| Internal API | `internal/api.py` | `POST /internal/messages/{msg}/pause/` added; the old approvals-poll GET deleted |
| Resume road | `chat/approvals.py` | decide_tool_approval + NEW answer_question write onto PausedRun.decisions (row-locked, once per call) → all decided → resume; preflight decide unchanged |
| api.py | `chat/api.py` | swarm branch deleted — several mentions = several single replies, each gated |
| Tests | `chat/tests.py` | rewritten where the contract changed: PausedRelayTests + ToolApprovalDecisionTests (pause-and-resume, incl. the two-pending test), queue-order test, done-extras test; swarm tests deleted; fixtures patched to the new modules |
| Garbage killed | `workspace/fixtures.py` | the chat↔workspace test-import circle is broken: InviteGrantsFixture moved to its own module, both test files import it, workspace/tests.py re-exports |

A paused reply is NOT an orphan: the reaper skips PAUSED rows (someone may
take a day to decide). A PausedRun whose relay died before storing the job
(restart between pause and decision) is failed politely on resume —
"please ask again".

**VERIFIED (owner, 2026-10-14):** migration 0031 applied; the WHOLE nucleus
suite ran end to end for the first time ever (the old test-import circle had
blocked full discovery) — **368 tests, all passed**. Every new Step 2 test
(pause/resume, the two-pending rule, queue order, done extras) passed on its
first run. The full run also surfaced and we fixed three PRE-EXISTING
problems: a dead debug command importing the long-renamed AIModel (retired to
.step0-removed/), the OAuth test fixture creating MCP servers without a
project (illegal since migration 0010 — two creates fixed), and a flaky hook
rate-limit test (30 fires could straddle a minute window — clock now frozen
in the test). **STEP 2 CLOSED.**

### Step 3 — AI features end to end (handoff changes 10 + 11, plus 2/3/7/14.6)
The embedder setting + reindex flow; embed calls updated (no more
type="code"); store output_type / render_as / embed_description on messages;
output_type in history; question cards + resume answers; nudges endpoint +
leftovers posted; durable approval rows (ruling 2.8).
**Done when:** a chart reply renders, a question pauses and the answer
resumes, a nudge reaches a running reply, approvals survive a restart.

**Step 3 scope (verified against the handoff + the built code, 2026-10-14).**
Already done in Step 2: output_type/render_as/embed_description stored (11.1),
used_tools/retrieved_sources stored (ch.8), queue-per-topic (11.7), nudges
endpoint + leftovers + nudge_taken relay (11.5), pause storage + the
answer_question service (11.4's engine half), memory-pass delete rule (11.6 —
the existing message delete covers tool memory). Ruling 2.8 (durable approval
rows) is SATISFIED by Step 2's PausedRun table + the metadata mirror — what
remains of it is pause EXPIRY (change 9), built here. Remaining, built now:

1. History rows gain `status` (change 2 — engine drops non-completed rows;
   output_type was already served).
2. Persona model seats + flags (changes 3 + 7 + 14.6): `router_model`,
   `deep_model` FKs, `delegation_enabled`, `tool_access` (all|selected),
   `approval_scope` (topic|requester_only) on Persona; a company DEFAULT
   router model on CompanyAIConfig, resolved INTO router_model before the
   persona is served. Migration 0032.
3. Per-project embedder setting (10.1): `Project.embedder` JSON (unset =
   system default fastembed); change restricted to COMPANY owner/admin via a
   new right `project.embedder` (COMPANY scope — Owner + Admin bundles).
4. Reindex flow (10.2): PUT the embedder → project locks
   (`Project.reindex_status="building"`; persona triggers in it are refused
   with a worded message) → POST /embed/reindex/ → poll status → unlock.
   A Celery task drives it; a crash is safe (old index stays active).
5. Embed calls updated (10.3 + 11.3): every embed POST carries the project's
   `embedder` spec; message embeds carry `used_tools`; rendered replies embed
   their `embed_description` (relay already did this); the dead
   GET /directives/ proxy in context/api.py is DELETED (engine dropped it).
   All engine calls now go through NexusAIClient — sync helpers added for
   celery/django callers (the one-door rule holds).
6. Question ANSWER endpoint (11.4): POST …/messages/{id}/questions/{call_id}/
   → chat/approvals.answer_question (built + tested in Step 2).
7. Pause expiry (change 9): hourly Celery beat task — a PausedRun older than
   24h gets deny ("expired — nobody decided within 24 hours") for undecided
   approvals and an empty answer for undecided questions, then resumes; the
   engine words the refusals and the reply completes instead of hanging
   forever.

**Built 2026-10-14 — what landed where:**

| Piece | File | Notes |
|---|---|---|
| Model fields | `nucleus/models/intelligence.py`, `workspace.py` + migration `0032_seats_embedder.py` | Persona: router_model, deep_model, tool_access, approval_scope, delegation_enabled; CompanyAIConfig: default_router_model; Project: embedder (JSON) + reindex_status |
| Internal API | `internal/api.py` | history rows carry `status`; PersonaInternal carries the seats (router RESOLVED through the company default, degrading like the advisor) + the three flags |
| Right | `authn/permissions/rights.py` | `project.embedder` — COMPANY scope on purpose (only company Owner/Admin reach it); Admin bundle; needs seed_permissions |
| Embedder endpoints | `workspace/api.py` | GET/PUT /projects/{id}/embedder/ — validate the spec, lock the project, queue the rebuild; 409 while one runs |
| Reindex driver | `intelligence/tasks.py` | `reindex_project` — start → poll → unlock; refusal/timeout marks "failed"; DEFAULT_EMBEDDER = local fastembed |
| Trigger fence | `chat/api.py` | personas refused with code "reindexing" while the project rebuilds |
| Client sync side | `chat/nexus_ai.py` | embed_document / delete_context_source / embed_recall / delete_recall_vector / delete_message_vector / start_reindex / reindex_status — context/services, recall and panel_providers now go through the client; the dead GET /directives/ proxy deleted from context/api.py |
| Embed payloads | `context/services.py`, `intelligence/recall.py`, `chat/relay.py`, `chat/api.py` | every embed carries the project's `embedder`; message embeds carry `used_tools` |
| Question endpoint | `chat/api.py` | POST …/messages/{id}/questions/{call_id}/ → answer_question |
| Pause expiry | `chat/tasks.py` (new) + beat entry in settings | hourly; people's own decisions are never overwritten |
| Loop-safety fix | `chat/relay.py` | `_lock_for` keeps the topic lock PER EVENT LOOP — async_to_sync callers (Celery: schedule fires, expiry) open a fresh loop per call, and an asyncio.Lock reused across loops raises; found while designing the expiry test |
| Tests | `internal/tests_step3.py` (4), `workspace/tests_embedder.py` (9), chat/tests.py Step 3 section (5) | 18 new tests |

**VERIFIED (owner, 2026-10-14):** migration 0032 applied; seed_permissions
added project.embedder; full suite **386 tests, all passed**. One first-run
bug, fixed: django-ninja reads a bare `payload: dict` on a PUT as a QUERY
param — the embedder body needed a proper Schema (EmbedderIn); everything
else — the reindex driver, pause expiry, question endpoint, seats, history
status — passed on the first run. **STEP 3 CLOSED.** The "done when" items
that need a real engine (a chart reply rendering, a live question card) ride
the switch-over (Step 8); every contract behind them is pinned by tests.

### Step 4 — Login and posture (rulings 2.1 + 2.7)
Supabase default + local fallback login; the owner CODE FLOW (sign in on our
portal, type the code into the install — replaces create_owner); DEBUG off,
generated SECRET_KEY, real ALLOWED_HOSTS/CORS, nginx serves media.
**Done when:** an install with no internet can still log in; a fresh install
is claimed with a code, no shell needed.

**Step 4 rulings (owner, 2026-10-14 — "yes, go"):**
1. **The code flow runs through OUR portal** (NEURALOPS_PORTAL_URL), using
   the two Supabase edge functions already named in settings
   (SUPABASE_DEVICE_REQUEST_URL / SUPABASE_DEVICE_POLL_URL). The fresh
   install shows a short code; the person signs in on the portal and types
   the code THERE; the install polls, and the first VERIFIED person becomes
   the owner. If the functions are dead or shaped differently, only
   `authn/portal.py` (or the two URL env vars) changes — the parsing is
   tolerant on purpose. `manage.py create_owner` STAYS as the air-gapped
   fallback and is named in the error when the portal is unreachable.
2. **Local passwords are per-user, set by each user in their own profile**;
   an owner/admin can reset someone else's (new right
   `company.local_password`). Local sign-in hands out a token signed by THIS
   server's SECRET_KEY — offline login never touches the network.
3. **Posture is safe by default:** DEBUG defaults OFF; with DEBUG off and no
   SECRET_KEY the server REFUSES to start, and the message says exactly what
   to do; SECRET_KEY joins init-secrets; ALLOWED_HOSTS/CORS gain env
   overrides (defaults stay open — the WHY is recorded below); nginx already
   served /media/ in both profiles (verified — nothing to change there).

**The portal contract (what nucleus sends and tolerates — pin the portal's
edge functions to this, or update authn/portal.py):**
- `POST SUPABASE_DEVICE_REQUEST_URL`, body `{server_url}`, anon key sent as
  `apikey` and `Authorization: Bearer` → `{code|user_code,
  request_id|device_code|id, expires_in?}` (expires_in defaults to 900).
- `POST SUPABASE_DEVICE_POLL_URL`, body `{request_id, device_code}` (the
  same id under both names) → while waiting: `{status: pending |
  authorization_pending | waiting}` or an empty status; once claimed:
  `{access_token|token}` — a REAL Supabase access token for the person who
  typed the code (nucleus verifies it with the same JWKS check as every
  sign-in); `{status: expired | denied | declined}` ends the attempt.

**Built 2026-10-15 — what landed where:**

| Piece | File | Notes |
|---|---|---|
| Portal client | `authn/portal.py` (new) | request_device_code / poll_device_code; tolerant keys; the ONLY file that knows the two URLs |
| Local tokens | `authn/local_auth.py` (new) | HS256 JWTs signed with SECRET_KEY; iss/aud "neuralops-local"; LOCAL_TOKEN_HOURS (24) |
| Either-token bearer | `authn/auth.py` | the token's alg header picks the check: HS256 → local (no network — this is what makes an air-gapped login work), anything else → Supabase; LOCAL_LOGIN_ENABLED=false closes the local door, already-issued local tokens included |
| The claim | `authn/services.py` | `claim_install()` — mirrors create_owner's creation block exactly (company + unique slug, CompanyAccess OWNER, the REAL RBAC Owner role, default groups) and runs seed_permissions itself, so the owner holds real rights the moment the claim returns |
| Setup endpoints | `authn/api.py` | GET `/auth/setup/status/` · POST `/auth/setup/start/` (hands out the code; 409 once owned; a dead portal answers 502 and names create_owner) · POST `/auth/setup/poll/` (pending → claimed; the portal's token is VERIFIED before anyone becomes owner; first verified claim wins, the second gets 409) |
| Local endpoints | `authn/api.py` | POST `/auth/local/signin/` (one failure message for every cause; braked — 10 tries per 5 minutes per address+email, counted in the signals store) · `/auth/local/set-password/` (your own; Django's password validators) · `/auth/local/reset-password/` (someone else's; right company.local_password; personas/ghosts refused) |
| Right | `authn/permissions/rights.py` | `company.local_password` — Owner + Admin bundles (needs `manage.py seed_permissions` once) |
| Posture | `core/settings.py` | DEBUG from env, default OFF; SECRET_KEY from env — dev-only fallback under DEBUG, otherwise boot REFUSED with the fix spelled out; ALLOWED_HOSTS / CORS_ALLOWED_ORIGINS env overrides; LOCAL_LOGIN_ENABLED / LOCAL_TOKEN_HOURS |
| init-secrets | `neuralops/entrypoint.sh` | now prints SECRET_KEY too; an EXISTING install appends one SECRET_KEY=... line to its secrets.env — never re-runs the generator (that would replace the live POSTGRES_PASSWORD) |
| Dev compose | `docker-compose.neuralops.yaml` | nucleus-dev + the two celery-dev services set DEBUG=true — dev keeps working exactly as before (recreate the three containers once to pick it up) |
| Tests | `authn/tests_step4.py` | 14 tests: the whole claim flow (status / code / pending / first claim with REAL rights after / second-claim 409 / dead-portal fallback message) + local passwords (set your own → sign in offline → the token opens a real endpoint, weak refused, wrong-vs-ghost identical, the brake, the off-switch, expiry, admin reset, persona guard) |

**Why ALLOWED_HOSTS/CORS default OPEN, recorded:** a self-hosted server is
reached by LAN addresses, Tailscale names and tunnels nobody can predict,
and the hosted web app (whatever origin it runs on) must be able to talk to
ANY install with a bearer token — no cookies ride on CORS here. Pinning
either by default would break the product's own sign-in on most installs;
both get env overrides (`ALLOWED_HOSTS=…`, `CORS_ALLOWED_ORIGINS=…`) for
deployments that want them pinned.

**Not nucleus's half (recorded so it isn't lost):** the portal's claim page
(the two edge functions + a "type your code" screen) and the app's setup /
local-login screens live outside this repo — the contract above and
FRONTEND-REVAMP §2.8 are their spec.

**VERIFIED (owner, 2026-10-15):** the three dev containers recreated with
DEBUG=true (the posture change landed without breaking dev);
seed_permissions now reports **48 rights** (46 at Step 1 + project.embedder
+ company.local_password); full suite **400 tests, all passed** — every
Step 4 test (the claim flow end to end, the second-claim 409, local
set/sign-in/reset, the 11th-try 429 brake, the LOCAL_LOGIN_ENABLED
off-switch killing even already-issued tokens, token expiry, the persona
guard) passed on the FIRST run, and the log shows the real roads firing:
"install claimed by founder@acme.test", "vera@acme.test signed in with a
local password", the brake's ten 401s then "Too Many Requests", and the
dead-portal "Bad Gateway" naming create_owner. **STEP 4 CLOSED.** The
"done when" halves that need the OUTSIDE pieces — a person really typing a
code at the portal page, the app's setup/login screens — ride on the portal
and frontend work, specced above and in FRONTEND-REVAMP §2.8.

### Step 5 — File viewer v1 (§3)
Browse, download, view-as-HTML over each project's folder.
**Done when:** the owner opens a project, sees the personas' files, downloads
one and views one in the browser.

**Step 5 build notes (2026-10-15):**
- The folder is `settings.PROJECTS_ROOT / "<slug>-<id8>"` — the SAME helper
  the terminal and project provisioning already use
  (workspace/services.get_project_folder_name), so the viewer always looks
  exactly where the personas write.
- Who may look: the same project road every other read uses (project.view,
  with the topic-reach fallback) — no new right needed.
- The wall: every path is resolved (symlinks FOLLOWED) and must land inside
  the project's folder — `..` and symlinks pointing out are refused with a
  400. A leading slash is read project-relative (friendly to frontends).
- Rendered views are size-capped (2 MB text, 8 MB images); binary is never
  "rendered" (415); too big says "download it instead" (413); downloads are
  streamed with no cap. Every rendered page is served with
  `Content-Security-Policy: sandbox` — the browser runs NO script from it,
  so a file a persona (or anyone) wrote cannot act in the viewer's browser.
- Markdown rendering + code highlighting use `markdown` and `Pygments` —
  added to requirements.txt but OPTIONAL at runtime: an image built before
  them shows the same content as readable escaped text instead (the tests
  pass either way). Rebuild the dev image when you want pretty rendering;
  the production image picks them up at its next build anyway (Step 8).

| Piece | File | Notes |
|---|---|---|
| The viewer | `workspace/files.py` (new) | list_folder / open_for_download / render_html; the wall; the caps |
| Endpoints | `workspace/api.py` | GET `/projects/{id}/files/?path=` (browse) · GET `/projects/{id}/files/content/?path=` (download) · `…&as=html` (view) |
| Renderer deps | `docker/dev/requirements.txt` | markdown + Pygments (optional at runtime — see note) |
| Tests | `workspace/tests_files.py` | 11 tests: browse order, subfolder, viewer-vs-outsider 404, no-folder 409, download bytes + attachment, kind mix-ups, the wall (`..` + symlink out), sandboxed markdown page, code view, 413 cap, 415 binary |

**VERIFIED (owner, 2026-10-15):** full suite **411 tests, all passed** —
every Step 5 test green on the FIRST run; the log shows the viewer's whole
refusal vocabulary firing for real (409 no folder · 404 missing · 413 too
big · 415 binary · 400 bad path / kind mix-ups). No migration, no new right
— nothing to seed. **STEP 5 CLOSED.** The "owner opens it in the browser"
half rides the frontend work (contract in FRONTEND-REVAMP §2.4); pretty
markdown/code rendering arrives free at the next image build (markdown +
Pygments are in requirements.txt, optional at runtime).

### Step 6 — Front doors (handoff changes 13 + 14)
The MCP gateway (per-user tokens), the "configure" topic + provisioning
fence, connector one-click toggles, the phone-home (open/close, one total),
stored tool lists, the OAuth roads. The three MCP servers themselves are
their own small projects on the MCP track.
**Done when:** Claude Desktop can use a NeuralOps install as a tool with a
personal token; the configure fence holds; the phone-home fires on open and
close.

**Step 6 rulings (owner, 2026-10-14/15 — settled in discussion):**
1. **The gateway lives INSIDE nucleus** (`/api/v1/mcp/`) — no new container,
   no new secret; tokens are checked right where the permissions live. The
   separate "neuralops-mcp" container idea is dropped for thin connectors;
   heavy connectors (data MCP, code-graph) keep their own compose services
   later.
2. **Gateway tokens are minted by FOUR roles only** — Company Owner, Company
   Admin, Project Owner, Project Admin — via a new right `gateway.token`
   (PROJECT scope, Owner+Admin bundles, same mechanics as the configure
   fence). A token is named, stored HASHED, shows last-used, and is
   revocable; company-level admins see and revoke every token; a token for a
   member still only ever acts AS that member through PermissionChecker —
   no token can do more than its person. `GATEWAY_ENABLED` (default on)
   turns the whole door off. No terminal command — Step 4's no-shell story
   holds.
3. **Internal calls need no token:** when a persona uses the gateway, the
   call carries X-Internal-Key (only the engine holds it) PLUS the id of the
   person whose run it is; the gateway enforces rights as that person.
   Nothing inside ever runs as a master user.
4. **Chains + the workflow MCP move to Step 7**, merged with runbooks — a
   chain definition and a runbook are the same thing; one table family,
   touched once.
5. **Phone-home collector = a Supabase edge function** (`{SUPABASE_URL}/
   functions/v1/phone-home`, env-overridable via NEURALOPS_PHONE_HOME_URL) —
   NOT a tailscale/private address (customers' installs must reach it on the
   public internet) and NOT the frontend domain (it's only a frontend). One
   total, on app open + close, identified by NEURALOPS_INSTALL_TOKEN, fails
   silently offline. The function itself is portal-side work; its contract
   is specced below.
6. **No separate company-configure place:** company-wide actions (create a
   project, company model configs) ride ANY project's configure topic — the
   provisioning tools act with the CALLER's rights, so a company owner/admin
   can do company-wide things from any configure topic and a project-only
   admin cannot. The rights draw the line; no extra screen.
7. **Stored tool lists (change 6):** fetched when a server is attached/saved
   plus a "Refresh tools" button — no background syncing in v1. A tool
   counts as read-only only if the server itself declares it; unlabeled =
   write (asks first).
8. **OAuth, three roads** (current flow verified in
   intelligence/oauth_client.py — a full per-server authorization-code flow
   with encrypted tokens + silent refresh already works):
   - **Famous shortlist (GitHub, Google Drive, Atlassian): one-click via the
     vendor's own "NeuralOps" apps + a relay page on the portal.** The
     provider only ever sees the portal's ONE address; the relay reads the
     signed state and bounces the person on to their own server; tokens are
     stored only on the customer's install (for providers that force a
     client secret, the exchange happens on the relay — the secret never
     ships in the public image — and tokens pass through, never stored).
     Nucleus ships the per-provider presets; the relay function + app
     registrations are portal-side, specced below; until they exist these
     providers simply show the paste-your-own road.
   - **Modern MCP servers: dynamic client registration** (the MCP standard)
     — the install introduces itself, callback = its own NEURALOPS_SERVER_URL;
     no pre-registered list anywhere.
   - **Everything else: paste-your-own client_id/secret** — already built,
     stays the universal/air-gapped fallback.

**Built, Part A — the gateway (2026-10-15):**

| Piece | File | Notes |
|---|---|---|
| Engine: message search | `nexus-ai fastapi_app/routers/search.py` (new) | POST `/api/v1/search/messages/` — the EXACT contract chat/search.py has called since 0.8.0 (it was a legacy-engine endpoint; without this, semantic chat search would silently degrade to literal at switch-over). Also serves the gateway's search_memory. Ranks only — nucleus filters by visibility. |
| Engine: tool listing | `nexus-ai fastapi_app/routers/mcp_tools.py` (new) | POST `/api/v1/mcp/tools/` {url, bearer_token?} → tools with name/one_line/read_only (readOnlyHint only; unlabeled → null = write). For change 6's attach-time fetch + Refresh button (nucleus half rides Part B). Any dial failure = one 502 + the reason. |
| Token table | `nucleus/models/gateway.py` + migration `0033_gateway_tokens.py` | GatewayToken: acts-as user, created_by, name, sha256 hash (shown once), last_used (written at most once/minute), soft revoke |
| Right | `authn/permissions/rights.py` | `gateway.token` — COMPANY object, PROJECT scope (the four-roles mechanics); Owner + Admin bundles; needs seed_permissions |
| Token endpoints | `gateway/api.py` | POST/GET/DELETE `/api/v1/gateway/tokens/` — four roles mint (company-level may mint FOR someone; project-level for self), everyone sees their own, company-level sees/revokes all |
| The MCP door | `gateway/api.py` | POST `/api/v1/mcp/` — stateless streamable-HTTP JSON-RPC: initialize / tools/list / tools/call / ping; notifications → 202; batch refused. Auth: Bearer nxg_… OR X-Internal-Key + X-NeuralOps-User (ruling 3 — the no-token inside road; permissions always as that person). GATEWAY_ENABLED=false → 403. |
| The five tools | `gateway/tools.py` | list_projects · list_topics · post_message · ask_persona (the REAL trigger road — rights, reindex fence, queue-per-topic; waits up to GATEWAY_ASK_TIMEOUT_SECONDS=180, then "still working" while the reply finishes into the topic) · search_memory (engine ranks, nucleus filters by the caller's visible topics, literal fallback). Thin front door only — every tool runs on existing roads. |
| Posture fix | `core/urls.py` | /media/ now served ALWAYS, not only under DEBUG — Step 4 turned DEBUG off in production and django's static() helper refuses when DEBUG is false; avatars would have 404'd behind nginx's /media/ proxy |
| Settings | `core/settings.py` | GATEWAY_ENABLED (default on), GATEWAY_ASK_TIMEOUT_SECONDS; INSTALLED_APPS + gateway |
| Tests | `gateway/tests.py` (10) + `nexus-ai tests/test_search_and_mcp_tools.py` (4) | four-roles minting incl. a project-level Admin; admins-see-all; the wire shape (initialize/list/call/notification/unknown); wrong+revoked+absent tokens 401; the internal road; the off switch; post_message + visibility; ask_persona returns the reply and keeps the rights fence; search filtered by visibility. Engine: ranking across projects, key gate, live dial with read hints, dead server 502. |

**Honest limit, recorded:** the engine's MCP capability sends ONE auth header
(authorization_token), so a persona using the gateway TODAY attaches it like
any MCP server (url `http://nucleus:8000/api/v1/mcp/` + a minted token). The
no-token internal road (key + user header) is built and tested nucleus-side;
teaching the engine's server rows to carry extra headers is a small engine
config change that rides later — recorded so it isn't lost.

**Part A VERIFIED (owner, 2026-10-15):** nucleus — migration 0033 applied;
seed_permissions reports **49 rights**; full suite **423 tests, all passed**,
every gateway test green on the first run (tokens minted per role,
wrong/revoked 401, off-switch 403, sara's revoke rules). Engine — **90
passed, 20 skipped** in the nexus-ai-debug container: the live MCP dial
(s6c/s6d) passed after one real-package fix — the pinned mcp 2.x client is
`mcp.client.streamable_http.streamable_http_client(url, *, http_client=…)`
yielding (read, write), with headers on a pre-built httpx2.AsyncClient —
probed live, not guessed. The 20 skips are the vector-db tests (test
postgres unreachable from that container — they skip by design); the two new
search tests execute in the vector-enabled setup that produced the earlier
"106 passed, 0 skipped" run — to be exercised there before switch-over.

**Built, Part B + the phone-home (2026-10-15):**

| Piece | File | Notes |
|---|---|---|
| Configure topic | `nucleus/models/workspace.py` (+is_configure) + migration `0034_configure_and_tools` + `workspace/services.create_project` | Every project is BORN with its reserved "configure" topic (in its general channel); the data half of 0034 backfills every existing project |
| The fence | `authn/permissions/row_rules.py` | `_configure_fence`: visible to exactly the project.update holders — the same four roles as token minting; enforced in visible_topics + visible_topic + visible_topic_ids, so EVERY road (lists, messages, search, the gateway) honours it from one place; a direct topic invite does NOT pierce it |
| Stored tool lists | `nucleus/models/intelligence.py` (MCPServer.tools) + same migration | [{name, description, read_only}]; read_only only from the server's own readOnlyHint, null = write (asks first) |
| The fetch | `chat/nexus_ai.py` (list_mcp_tools) + `intelligence/api.py` | fetched through the engine at CREATE and PATCH (best-effort — a dead server never fails a save) + POST `/mcp-servers/{id}/tools/refresh/` (the button; 502 carries the dial's reason verbatim); bearer rule mirrors the engine's (oauth2 → user token, static → client_secret) |
| Shipped to the engine | `internal/api.py` (MCPServerInternal.tools) + `intelligence/schema.py` (MCPServerOut.tools) | the engine already consumed a stored `tools` list (its Layer 1 dial tests) — nucleus now actually sends it |
| Phone-home | `core/phone_home.py` (new) + `core/asgi.py` + settings | ruling 5 verbatim: ONE total (input+output tokens, all time), install token, on open (background thread) + close (atexit); wired in asgi.py so manage.py/tests/celery NEVER send; fails silently offline; default collector `{SUPABASE_URL}/functions/v1/phone-home`, env-overridable. The edge function's contract is in core/phone_home.py's docstring — portal-side work, like the claim page |
| Toggles — scope ruling | (recorded, not built) | a one-click toggle for the data/code-graph/provisioning connectors would today enable rows pointing at services that DON'T EXIST YET (they're their own projects on the MCP track) — a dead switch is a lie, so the toggles ship WITH those connectors; the W11 catalog + the attach flow already cover real external servers |
| Tests | `workspace/tests_step6.py` (10) | the configure birth + backfill; the fence on every road incl. the direct-invite case and the four roles; refresh stores/gates/502s; internal rows left alone; the engine payload carries the list; phone-home sends one total and is silent offline |

**Part B VERIFIED (owner, 2026-10-15):** migrations 0034+0035 applied (the
first attempt taught a real lesson, kept in 0034's header: adding an indexed
column and backfilling rows in ONE migration trips postgres — schema and
data are now separate migrations); full suite **433 tests, all passed**. The
first run surfaced one genuine fence bug — can() RAISES on an unregistered
right, so a minimal registry (a fixture, or a server that hasn't re-seeded)
crashed every topic list — fixed by failing CLOSED: the configure topic
stays hidden instead. The log shows the new roads live: tools-refresh 502 on
a dead dial, 403 for a Member, configure backfill.

**Built, Part C — the OAuth roads (2026-10-15):**

| Piece | File | Notes |
|---|---|---|
| PKCE on every road | `intelligence/oauth_client.py` | authlib `code_challenge_method="S256"`; the code_verifier travels inside the SIGNED, 10-minute state (django signing, salt `mcp-oauth-state`) and `complete_callback` hands it to the token exchange. Mandatory for the public clients road 1 creates, harmless on the pasted road |
| Road 1: dynamic client registration | `intelligence/oauth_client.py` `ensure_client(server)` | On the Connect click, a server row with nothing pasted gets DISCOVERED (`/.well-known/oauth-protected-resource` → authorization_servers[0], else the origin itself; then `oauth-authorization-server`, falling back to `openid-configuration`) and nucleus REGISTERS ITSELF: `{client_name: "NeuralOps", redirect_uris: [own callback], grant_types: [authorization_code, refresh_token], token_endpoint_auth_method: "none"}`. client_id lands in oauth_config; a returned client_secret goes into encrypted secrets, never plain config. Never raises — (False, a plain-words reason) |
| Wired into Connect | `intelligence/api.py` `mcp_oauth_authorize` | `ensure_client` runs before the URL is built; a provider without registration (or dead discovery) → **502 with the reason verbatim** telling the admin to paste their own app — the universal fallback stays one sentence away |
| Road 2: the portal relay mode | `intelligence/oauth_client.py` `_redirect_uri(cfg)` | `oauth_config.redirect_mode = "portal_relay"` → the provider bounces to `{NEURALOPS_PORTAL_URL}/oauth/relay`; the state now carries `server_url` so the relay knows where home is (contract below) |
| Vendor presets — the famous three ONLY | `intelligence/mcp_catalog.py` + `intelligence/schema.py` (MCPCatalogEntryOut.oauth_preset) | github / atlassian / google-drive entries carry `oauth_preset` (endpoints, scopes, the refresh-token-forcing authorize params, redirect_mode portal_relay, token_env_var). `client_id` ships EMPTY until the vendor "NeuralOps" apps are registered (portal-side) — an empty one means the app shows only paste-your-own. The client SECRET never appears in the catalog and never ships in the image. GitHub's preset is marked: its exchange demands the secret even with PKCE, so it waits for the relay-exchange variant |
| Tests | `intelligence/tests_oauth_dyn.py` (9) | registration fills the client + keeps the secret encrypted; a pasted config makes zero requests; no-registration → clear refusal, 502 through the API; the Connect click auto-registers end-to-end and the URL carries code_challenge + S256; relay mode points at the portal and the state's base64 segment is readable WITHOUT the key (the relay's whole trick — proven by decoding it both ways); the callback exchange carries the code_verifier out of state; presets exist for exactly the three and carry no secret |

**The portal relay's contract (portal-side work, written here first):**

- **v1 — pure forwarder** (enough for every PKCE provider): one public page
  `{NEURALOPS_PORTAL_URL}/oauth/relay`. It receives the provider's
  `?code=…&state=…`, splits the state on `:` and base64url-decodes the FIRST
  segment (django signing's payload is readable without any key — the format
  is `payload:timestamp:signature`, payload urlsafe-base64 with padding
  stripped; a `.`-prefixed payload is zlib-compressed first), reads
  `server_url` out of it, and bounces the browser to
  `{server_url}/api/v1/mcp-servers/oauth/callback/?code=…&state=…` — where
  the signature IS verified (wrong/old/forged state dies there) and the PKCE
  exchange happens on the customer's own server. The relay verifies nothing,
  exchanges nothing, stores nothing, logs nothing.
- **v2 — relay-exchange** (only for providers that force a client secret,
  GitHub among them): the relay itself exchanges the code using the vendor
  app's secret (a portal-side env var, never in any image) and forwards the
  resulting tokens to the same customer callback in one redirect. Tokens pass
  through, never stored — ruling 8's honesty note stands. Specced only; built
  when the vendor apps are registered.

**Part C VERIFIED (owner, 2026-10-15):** full suite **442 tests, all
passed** on the first run — no migration, no new right, pure code. The log
shows the roads live: the 502 on `/oauth/authorize/` when a provider offers
no self-registration (the reason the UI will show verbatim), and the
existing OAuth tests (paste-your-own road) untouched by PKCE riding the
state.

**STEP 6 CLOSED (2026-10-15).** All three parts verified: the gateway front
door + tokens (A, 423), the configure topic + stored tool lists + phone-home
(B, 433), the OAuth roads (C, 442). Left deliberately portal-side (specced
above, not nucleus work): the claim page, the phone-home edge function, the
oauth relay, and the three vendor app registrations. Left as recorded engine
work: extra-headers config for the gateway's no-token internal road; the two
engine search tests to be exercised on the vector-enabled setup before
switch-over.

### Step 7 — Scheduling trio + chains (handoff changes 12 + 14, ruling 2.6)
Schedules fire triggers with interactive=false (verify-first read);
runbooks become saved chain definitions; routines stay per-turn presets;
overlaps removed. **Chains + the workflow MCP's nucleus half moved here from
Step 6 (Step 6 ruling 4)** — chain state + checkpoints, supervisor verdicts,
bounded redo, the default chain template — because a chain definition and a
runbook are one table family, touched once.
**Done when:** a scheduled run fires unattended, a saved chain reruns, and a
two-stage chain runs supervised end to end.

### Step 8 — Switch-over and distribution (§5)
Point the stack at the new engine module, retire the legacy one, ship the
unified image.

---

## 5. DISTRIBUTION (owner, 2026-10-14) — one app image, compiled files only

How the product ships once nucleus is done:
- **One app image** containing nexus-ai + nucleus + centrifugo (the compose
  file already builds toward this — one shared `neuralops` image, each service
  just a different `command:`). Postgres/redis/nginx stay official images.
- **Only compiled Python (.pyc) inside** — no .py source ships to customers.
  Build step: compile everything (`python -m compileall`, bytecode-only
  layout), strip the source files, keep migrations working (they compile like
  any module). The dev profile keeps bind-mounted source as today.
- Installed with docker compose; secrets generated once per install
  (init-secrets, now including SECRET_KEY — ruling 2.7); the owner claims the
  install with the code flow (ruling 2.1).
- Honest note, recorded: .pyc hides the source from casual eyes but is not
  encryption — bytecode can be decompiled with effort. It raises the fence;
  it is not a lock. The real protections stay the license/identity anchor
  (Supabase + install token) and the phone-home.

---

## 6. The frontend document

The UI's half of all of this lives in **`docs/FRONTEND-REVAMP.md`**: the
event/status contract the relay sends, every new screen or card the revamp
needs, and the rule that contract changes land in that document BEFORE code.
