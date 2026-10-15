# NeuralOps Nexus — the change prompt

**Document version: 1.0 (2026-10-15, at the close of Step 7).**
This file is VERSIONED: every session that changes the system must also
update this file (status, counts, new pieces) and add a row here.

| Version | Date | What changed |
|---|---|---|
| 1.4 | 2026-10-15 | Added `docs/FRONTEND-CHANGE-PROMPT.md` (v0.1 — the frontend's own brief; its §6 fills once the react repo is cloned locally) |
| 1.3 | 2026-10-15 | Doc cleanup (owner): the live set is now SIX files (below); every pre-revamp/consumed doc moved to `docs/_archive/` (history, not instructions — owner may delete) |
| 1.2 | 2026-10-15 | Added `docs/API.md` (every endpoint, internal and external, Postman-ready) to the doc set |
| 1.1 | 2026-10-15 | Added `docs/TESTS.md` (the test catalog) to the doc set; tests are guarantees — every new test lands with a row there |
| 1.0 | 2026-10-15 | First full version — Steps 0–7 closed, 457 nucleus tests, migrations through 0036, 49 rights |

Give this file to the assistant at the start of any session that will change
this codebase. It says what the system is, how it is built, how every change
must be made, and where every detail lives.

---

## 1. What this product is

**NeuralOps Nexus** — a self-hosted, multi-tenant AI chat workspace a company
runs on its OWN server. People and AI personas talk in projects → channels →
topics. Personas are real model-backed identities with tools (MCP servers and
in-process capabilities), memory (vector search over chats/docs/recall),
schedules, runbooks/chains, and inbound hooks. The business identity anchor is
the NeuralOps portal (neuralopsnexus.ai, Supabase-backed): installs are
claimed there, phone-home reports there, OAuth can relay through there — but a
customer's server works offline except for those portal touches.

Two code modules, one repo at **`/data/code/neuralops-forked`** (reached via
the node3-neuralops-forked file tools):

- **`modules/nexus-nucleus`** — the Django backend (the product's brain):
  auth, rights, workspace, chat orchestration, intelligence config, gateway,
  scheduling, billing/usage, phone-home.
- **`modules/nexus-ai`** — the REBUILT engine (FastAPI + pydantic-ai): takes a
  TriggerJob, builds the prompt and toolsets, runs the model, streams events
  back. It replaces a legacy engine ("0.8.0", in `nexus-ai-legacy`) that
  production still points at until Step 8's switch-over.

The frontend is a separate app; its contract lives in
**`docs/FRONTEND-REVAMP.md`** — contract changes land in that document BEFORE
code.

---

## 2. THE METHOD (non-negotiable)

1. **Settle each change in discussion first** — short questions, one at a
   time, with a recommendation. The owner rules; rulings are recorded
   verbatim-ish in `docs/NUCLEUS-REVAMP.md` under the step they belong to.
2. **Write the design into `docs/NUCLEUS-REVAMP.md`** before building.
3. **Build with acceptance tests** — every behavior gets a test in the same
   change.
4. **The owner verifies**: you hand him exact commands (below), he runs them
   on node3 and pastes the output.
5. **Record VERIFIED / CLOSED in the doc** only after his green paste.
6. **Verify-first, always**: read the actual code and quote file:line before
   claiming how anything works. NEVER guess a library's API — probe it live
   (e.g. `pkgutil.iter_modules` / `dir()` / `inspect.signature` inside the
   container) when docs and memory disagree.
7. **Keep language easy.** The owner is sharp but not a native English
   speaker; he once asked for Urdu when an explanation got too technical.
   Short sentences, plain words, no stacked jargon.

**The live doc set (all under `docs/`) — six files, owner's cut 2026-10-15:**

1. `CHANGE-PROMPT.md` — this file: the brief for any change session.
2. `NUCLEUS-REVAMP.md` — the master record: all rulings, built tables,
   VERIFIED blocks, steps 0–8, the distribution ruling §5, the portal
   contracts (claim flow, phone-home, OAuth relay).
3. `API.md` — every endpoint (user, public, gateway, internal, engine) with
   auth style and rights; an endpoint change lands there in the same change;
   live schemas at `/api/v1/openapi.json` for Postman.
4. `TESTS.md` — the test catalog; a new test lands with a row there, and
   weakening a test needs the owner's ruling.
5. `FRONTEND-REVAMP.md` — the UI's spec (the frontend is NOT built yet);
   contract changes land THERE before code.
6. `CONCEPTS-AND-ROLES.md` — the product's concepts and the rights/roles
   model, in plain language.
7. `FRONTEND-CHANGE-PROMPT.md` — the frontend's own change brief (the
   sibling of this file, for `neuralops-react-app` sessions).

Everything else (the engine rebuild plan NEXUS-AI-REVAMP, the handoff list
NUCLEUS-HANDOFF, OPEN-ITEMS, the pre-revamp ARCHITECTURE/DECISIONS/catalogs/
stories) lives in `docs/_archive/` — kept as history and for citations in
the live docs, never as instructions; the owner may delete the folder. A new
doc is added to the live set only with the owner's ruling, and each live doc
is versioned with its own changelog.

---

## 2b. Architecture — the owner's standing principles

These are the load-bearing design instructions behind everything. A change
that bends one of these needs the owner to re-rule first.

1. **Self-hosted first.** The customer's server is the product. Nothing
   leaves their network except: login to Supabase (unless offline/local
   login), the portal setup/OAuth-relay touches, and phone-home's ONE total.
2. **One trigger road.** Every AI reply — mention, schedule, chain step,
   supervisor review, gateway ask — goes through
   `chat/services.trigger_ai_response_async`. Never a second road.
3. **One client per direction.** Nucleus → engine: `NexusAIClient`
   (chat/nexus_ai.py) — the only file knowing NEXUS_AI_URL. Engine →
   nucleus: `NucleusClient` (ai_engine/core/nucleus_client.py) — the only
   file knowing the internal API. One place each for keys, timeouts, errors.
4. **Rights-as-the-person, everywhere; no master user.** Every door (API,
   gateway token, internal road, schedule, chain, hook) resolves to a REAL
   person first, and PermissionChecker + row visibility decide — the
   gateway, schedules and chains are thin front doors over existing roads,
   never new business logic. An invisible thing answers like a nonexistent
   one. Rights fences FAIL CLOSED.
5. **No shell steps for customers.** Setup is the portal code flow; tokens
   are minted in the UI by the four roles; `create_owner` stays only as the
   named air-gapped fallback. ("The four roles" = company owner/admin +
   project owner/admin, via project-scoped rights.)
6. **Nucleus orchestrates; the engine thinks.** Nucleus never resolves
   models/prompts/history — the engine pulls those itself through the
   internal API. The wire names are kept byte-for-byte from 0.8.0 so the
   two sides can ship separately.
7. **Contracts in docs BEFORE code** — frontend events in FRONTEND-REVAMP,
   portal pieces in NUCLEUS-REVAMP; the doc is the spec the other team
   builds against.
8. **Money is always estimated** (labeled), rows have no FKs, and every
   secret is Fernet-encrypted at rest and never returned by any API.
9. **Plain language** in docs, errors and UI copy — an error names what to
   DO ("paste your own client_id", "run it by hand").
10. **Verify-first** — read code, quote file:line, probe libraries live.

## 2c. The shape — flow and class diagrams

**The flow (one reply's life):**

```
person types "@Sara …" ──→ chat/api.py (rights: persona.mention, reindex fence)
   │                                │
   │                                ▼
   │          chat/services.trigger_ai_response_async  ←── schedules (interactive=False)
   │                │  pre-creates reply row                ←─ chains/_run_step + _review
   │                ▼                                       ←─ gateway ask_persona
   │          NexusAIClient ── POST /api/v1/trigger/ (TriggerJob, SSE) ──→ nexus-ai
   │                │                                                        │ pulls persona/history
   │                ▼                                                        ▼ via internal API
   │           chat/relay.py ←── 13 event types (delta/done/paused/…) ── engine run
   │                │ queue-per-topic, statuses, pause→PausedRun
   │                ▼
   └──→ Centrifugo ──→ the browser          usage batch ──→ POST /internal/usage/ ─→ UsageRecord
```

Outside doors: MCP clients → `POST /api/v1/mcp/` (Bearer nxg_…) → gateway
tools → the same roads. Webhooks → `/api/v1/hooks/{token}/` → a mention as
the hook's creator. Celery beat → schedules/expiries.

**The class diagram (main models and relations):**

```mermaid
classDiagram
  Company "1" --> "*" Project
  Company "1" --> "*" CompanyAccess
  CompanyAccess --> User
  Company "1" --> "1" CompanyAIConfig
  Project "1" --> "*" Channel
  Channel "1" --> "*" ChatTopic : is_configure flag
  ChatTopic "1" --> "*" ChatMessage
  ChatTopic "1" --> "*" TopicContext
  Project "1" --> "*" Persona
  Persona --> User : identity_user (shadow)
  Persona --> ModelConfig : model / advisor / router / deep
  Persona "*" --> "*" MCPServer : tools
  Persona "*" --> "*" ModelConfig : fallbacks (0..3, ordered)
  Company "1" --> "*" ModelConfig
  ModelConfig "*" --> "*" Project : attached (visibility)
  Project "1" --> "*" MCPServer : internal capabilities + external servers
  Project "1" --> "*" Routine : 4 built-ins seeded
  Project "1" --> "*" Runbook : chains; supervisor → Persona; redo_limit
  Runbook "1" --> "*" RunbookRun : status queued/running/waiting/done/failed/stopped
  RunbookRun --> ChatTopic
  ChatTopic "1" --> "*" PersonaSchedule : fires persona OR runbook
  ChatTopic "1" --> "*" InboundHook
  Project "1" --> "*" RecallEntry
  Project "1" --> "*" Deliverable
  ChatMessage "1" --> "0..1" PausedRun : approvals and questions
  User "1" --> "*" GatewayToken : acts-as; sha256 stored
  Company "1" --> "*" Role
  Role "*" --> "*" Right : RoleRight
  User "*" --> "*" Role : RoleAssignment at company/project/topic scope
  class UsageRecord { no FKs on purpose; ids as plain columns }
  class ModelPrice { local price catalog }
```

(Not drawn: Prompt/PromptTemplate on Persona, ChatSession/ChatReadMarker,
avatars, Invitation — see `nucleus/models/`.)

## 2d. Project structure

```
/data/code/neuralops-forked
├─ docs/                      NUCLEUS-REVAMP.md · NUCLEUS-HANDOFF.md ·
│                             FRONTEND-REVAMP.md · NEXUS-AI-REVAMP.md ·
│                             OPEN-ITEMS.md · CHANGE-PROMPT.md (this file)
├─ neuralops/                 install kit: compose, entrypoint.sh
│                             (init-secrets), secrets.env (NEVER regenerate)
├─ docker-compose.neuralops.yaml   the dev stack
└─ modules/
   ├─ nexus-nucleus/          Django backend (Python 3.11 in the container)
   │  ├─ core/                settings · urls · celery · asgi · phone_home
   │  ├─ nucleus/             models/ (account, workspace, intelligence,
   │  │                       scheduling, governance, context, prompt,
   │  │                       extended, gateway, usage, runtime) ·
   │  │                       migrations/ 0001→0036
   │  ├─ authn/               auth · portal · local_auth · permissions/
   │  ├─ workspace/           projects/channels/topics · files.py viewer ·
   │  │                       deliverables · terminal/browser tickets
   │  ├─ chat/                directives · realtime · messages · approvals ·
   │  │                       nexus_ai (client) · relay · search · tasks ·
   │  │                       services (shim + trigger road)
   │  ├─ intelligence/        api · services · schema · oauth_client ·
   │  │                       mcp_catalog · persona_catalog · pricing ·
   │  │                       usage_api · recall · tasks · builtin_routines
   │  ├─ scheduling/          api · services · tasks · runbooks (chains) ·
   │  │                       hooks · hooks_api · schema
   │  ├─ gateway/             api (MCP door + tokens) · tools (the eight)
   │  ├─ internal/            the engine's private API
   │  ├─ context/             topic context sources
   │  ├─ docker/              dev/ fat/ production/ (requirements + Dockerfiles)
   │  └─ .step0-removed/      retired code, owner may delete
   └─ nexus-ai/               the rebuilt engine (Python 3.13)
      ├─ fastapi_app/         main · contracts/trigger.py · routers/
      │                       (trigger, embed, models, search, mcp_tools) ·
      │                       stream/event_stream
      ├─ ai_engine/           core/ (ai_system, nucleus_client, specs,
      │                       turn_rules, billing, config) · context/ ·
      │                       output_types/ · prompts/ · vector_db/ ·
      │                       pydantic_ai_system/ (+tools/)
      ├─ tests/               fakes + 24 test modules
      └─ requirements.txt · requirements.lock · requirements-dev.txt
```

---

## 3. Where it runs (node3) and the verify commands

Dev stack is docker compose; the containers the owner actually has:

| Container | What |
|---|---|
| `neuralops-nucleus-dev` | Django backend (venv at `/opt/venv/nucleus-env`, code at `/nexus/nucleus`) |
| `nexus-ai-debug` | the REBUILT engine (image nexus-ai-test:1.0, bind-mounted live source at `/nexus/ai`) — NOT "neuralops-nexus-ai-new", that container does not exist |
| postgres (dev) | plain postgres today; production switch-over plans `pgvector/pgvector:0.8.7-pg17` |
| redis, centrifugo (`centrifugo-dev`), celery worker + beat | the usual |

**Nucleus commands (run from anywhere on node3, root ok):**

```
# migrate (only when a change adds a migration)
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py migrate nucleus

# reseed rights (only when a change adds/renames a right)
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py seed_permissions

# the full suite — ALWAYS with --noinput (a stale test DB once caused EOFError on the confirm prompt)
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py test -v 1 --noinput > test-output.txt 2>&1; tail -5 test-output.txt
```

**Engine suite:**

```
docker exec -w /nexus/ai nexus-ai-debug python -m pytest -q 2>&1 | tail -5
```

Current green baselines (2026-10-15): **nucleus 457 tests OK**, rights
registry **49**, migrations through **0036**; **engine 90 passed, 20
skipped** in nexus-ai-debug (the 20 are vector-db tests — the test postgres is
unreachable from that container, they skip by design; they and the two search
tests run in the owner's vector-enabled setup — exercise there before
switch-over). Any change must end at ≥ these numbers, all green.

---

## 4. nexus-nucleus — the map

Django 5.2 + django-ninja (Pydantic v2 schemas), async-capable endpoints, all
multi-tenant-scoped through one active `Company` row. API mounted at
`/api/v1/` (see `core/urls.py`): `/auth/`, `/me/`, `/roles/`, `/members/`,
`/projects/` (workspace + chat + context + scheduling + usage routers),
`/search/`, intelligence at root, `/internal/`, `/usage/company/`, `/hooks/`
(public — the token in the path is the credential), `/mcp` (the gateway) and
`/gateway/tokens/`. `/media/` is served ALWAYS (not only under DEBUG — Step 6
posture fix). Django admin at `/admin/`.

### Apps

- **`authn/`** — Supabase JWT auth (`auth.py` SupabaseBearer dispatches on the
  JWT alg header: HS256 → LOCAL token verified with SECRET_KEY, no network;
  else Supabase), portal device-code setup (`portal.py` — the ONLY file that
  knows SUPABASE_DEVICE_REQUEST_URL / SUPABASE_DEVICE_POLL_URL; the tolerant
  request/poll contract is written in NUCLEUS-REVAMP Step 4; a dead portal
  answers 502 naming the `manage.py create_owner` air-gapped fallback, which
  STAYS; `services.py`: claim_install mirrors create_owner + runs
  seed_permissions so the owner holds real rights at once), local/offline
  login (`local_auth.py`, 24h HS256 tokens,
  iss/aud "neuralops-local"; `LOCAL_LOGIN_ENABLED` kills it; signin throttled
  10/5min per addr+email), password set/reset endpoints, avatars.
  **`authn/permissions/`** is the rights system: `rights.py` the registry (49
  rights, each with object type + scope), `checker.py` PermissionChecker
  (NOTE: `.can()` RAISES ValueError on an unregistered right code — any new
  right used inside row_rules/fences must fail CLOSED via try/except),
  `row_rules.py` row visibility (visible_projects/channels/topics/personas/
  mcp_servers… + `_configure_fence`), `models.py` Role/Right/RoleRight/
  RoleAssignment. Four default role bundles: Owner, Admin, Member, Viewer;
  `manage.py seed_permissions` seeds/updates them. "The four roles" in
  rulings = company owner/admin + project owner/admin = whoever holds the
  project-scoped right (e.g. project.update, gateway.token).
- **`workspace/`** — projects/channels/topics/members/invites
  (`services.py`: create_project births the general channel, the fenced
  "configure" topic, the "Draft and review" template chain, legacy
  ProjectMember + Admin RoleAssignment; provision_project_folder_and_mcp
  makes the project folder + ONE internal MCPServer row carrying the four
  capabilities filesystem/shell/web_search/web_fetch), deliverables, the
  terminal/browser session tickets (HMAC, 60s), and **`files.py`** — the file
  viewer (Step 5): resolve_path wall (symlinks resolved, must land inside
  `PROJECTS_ROOT/<slug>-<id8>`), browse + download + view-as-HTML with CSP
  "sandbox", caps 2MB text / 8MB images, 415 binary, markdown/Pygments
  optional with escaped-pre fallback.
- **`chat/`** — split in Step 2 from a 1,777-line services.py into one-job
  modules: `directives.py` (@mention/@session/output-type//routine parsing),
  `realtime.py` (publish/publish_async/topic_channel → centrifugo),
  `messages.py` (create/update/fail AI message, user/system messages,
  serialise, orphan reaper — which SKIPS paused rows, sessions),
  `approvals.py` (preflight plans + tool approvals + answer_question —
  decisions write onto PausedRun, row-locked once per call; when EVERY
  pending call is decided the run resumes), `nexus_ai.py` (**NexusAIClient**
  — the ONLY file that knows NEXUS_AI_URL: stream_trigger (SSE + stop),
  resume, embeds, reindex, model check, list_mcp_tools — the one-door rule),
  `relay.py` (one reply's whole life: all 13 engine event types,
  queue-per-topic locks, PENDING→STREAMING→terminal, pause parks the job on
  PausedRun), `search.py` (engine ranks, nucleus filters by visibility,
  literal fallback), `tasks.py` (expire_paused_runs hourly, 24h: deny
  undecided approvals, "(no answer…)" for questions, then resume),
  `services.py` (a thin re-export shim + `trigger_ai_response_async` — THE
  one trigger road every AI reply takes: live @mention, schedule, chain
  step, supervisor review, gateway ask_persona; `interactive=False`
  suppresses preflight and makes the engine withhold ask_user/nudges).
  **Pause-and-resume contract:** the engine POSTs
  `/internal/messages/{msg_id}/pause/` `{job_id, topic_id, persona_id,
  state, catalog_hash, pending:[{call_id, tool, capability_id,
  args_preview, kind: approval|question}], role}` BEFORE message_paused;
  nucleus stores it in PausedRun (the state JSON never rides to the
  browser); a resume re-sends the ORIGINAL trigger job + `resume: {state,
  approvals, answers, role}` on the same trigger endpoint. Question answers:
  POST `…/messages/{id}/questions/{call_id}/`.
- **`intelligence/`** — ModelConfig (provider + BARE model_id, Fernet API
  key; `model_config` is a RESERVED Pydantic name — the FK is `model`;
  admin price overrides input/cached/output per million), Persona model
  SEATS + flags (Step 3): `router_model`, `deep_model`, `advisor_model`,
  fallbacks (0..3), `delegation_enabled`, `tool_access` (all|selected),
  `approval_scope` (topic|requester_only); CompanyAIConfig holds the company
  default router + the utility model (the server's own small jobs),
  MCPServer (internal capability rows vs external servers; secrets_encrypted
  Fernet JSON; `tools` = stored tool list fetched through the engine at
  create/patch + POST `/mcp-servers/{id}/tools/refresh/`, 502 reason shown
  verbatim), Persona (project-owned, model + advisor + fallbacks + mcp_servers
  + tool_levels + acts_after_approval + recall), Routine (the `/` presets,
  four built-ins per project), Recall, usage/pricing (money ALWAYS labeled
  estimated), **`oauth_client.py`** — the three OAuth roads (Step 6C): PKCE on
  every road (verifier in the signed state, salt "mcp-oauth-state", 600s),
  `ensure_client()` dynamic client registration (discovery via
  /.well-known/oauth-protected-resource → oauth-authorization-server →
  openid-configuration; registers `{client_name: "NeuralOps",
  token_endpoint_auth_method: "none"}`), `redirect_mode: "portal_relay"` →
  `{NEURALOPS_PORTAL_URL}/oauth/relay` with `server_url` readable in the
  state's base64 payload (django signing is signed, not encrypted — the
  relay's whole trick), paste-your-own as universal fallback.
  `mcp_catalog.py` hand-kept catalog; `oauth_preset` on exactly github /
  atlassian / google-drive (client_id EMPTY until the vendor apps are
  registered portal-side; the client SECRET never ships anywhere).
  **Money (Step 1):** `nucleus/models/usage.py` UsageRecord (one row per
  model call, the engine's field names kept byte for byte; **NO foreign
  keys on purpose** — billing rows must survive any deletion, and
  delegation ids like "msg:cp0" are not FK-able) + ModelPrice (local
  catalog, refreshed daily from MODEL_PRICES_URL, fails silently offline);
  `pricing.py` (override → catalog → cost null, exact Decimal; cache
  writes priced at the input rate); write endpoint POST /internal/usage/
  pushes live `usage_totals` events; reads in `usage_api.py` gated by
  `usage.view_project` / `usage.view_company`; EVERY money figure carries
  "estimated — prices not confirmed".
  **Embedder/reindex (Step 3):** `Project.embedder` JSON (unset = fastembed
  default), changed only under the COMPANY-scope right `project.embedder`;
  PUT locks the project (`reindex_status="building"` — persona triggers in
  it are refused with code "reindexing"), `intelligence/tasks.py
  reindex_project` drives start→poll→unlock, a crash leaves the old index
  active.
- **`internal/`** — the engine's private API (X-Internal-Key): persona
  payloads WITH credentials (model keys, MCP secrets after
  oauth_client.refresh_if_needed, tools list, tool_levels, utility/router
  models, fallbacks), topic history, recall writes, usage writes, pause/resume
  state.
- **`gateway/`** — Step 6: this server AS an MCP tool. POST `/api/v1/mcp/` =
  stateless streamable-HTTP JSON-RPC (initialize / tools/list / tools/call /
  ping; notifications→202; batch refused; GET→405). Auth: Bearer `nxg_…`
  personal token (sha256-stored, shown once, minted by the four roles via
  `gateway.token`) OR X-Internal-Key + X-NeuralOps-User (the inside road) —
  every call runs AS a real person with their rights. Eight tools:
  list_projects, list_topics, post_message, ask_persona (waits up to
  GATEWAY_ASK_TIMEOUT_SECONDS=180, never cancels), search_memory,
  list_chains, run_chain, chain_status. GATEWAY_ENABLED=false closes the door.
- **`scheduling/`** — PersonaSchedule (django-celery-beat DatabaseScheduler;
  creator is the actor, re-checked at every fire; fires with
  interactive=False), inbound hooks (public token URLs, rate-limited),
  **runbooks = CHAINS** (Step 7): steps `kind: "persona"` or
  `kind: "checkpoint"` (1–12, validated as one document in `runbooks.py`);
  one optional supervisor persona reviews EVERY stage (verdict APPROVE /
  REDO+notes / FAIL as a visible reply; unclear = stands; redo_limit 0–2,
  exhaustion → the step's on_failure stop/skip); checkpoints park the run
  WAITING (Celery slot released), answered by the starter or project.update
  holders at POST `…/runbooks/runs/{id}/checkpoint/`, answer joins the next
  step's context, 24h expiry task hourly; a checkpoint chain CANNOT be
  scheduled (refused at creation AND at fire time); run lifecycle is
  claim-guarded (QUEUED→RUNNING, WAITING→QUEUED) against double delivery.
- **`context/`** — attached context sources per topic (docs/code/chat/recall).
- **`nucleus/`** — all models (`models/`: account, workspace incl.
  ChatTopic.is_configure, intelligence, scheduling incl. Runbook/RunbookRun,
  governance, context, prompt, extended, gateway) and `migrations/` (0001 →
  **0036_chains**).
- **`core/`** — settings, urls, celery app, asgi (wires phone-home),
  **`phone_home.py`**: ONE total ever leaves the server —
  `{install_token, event: open|close, total_tokens}` to
  `NEURALOPS_PHONE_HOME_URL` (default `{SUPABASE_URL}/functions/v1/phone-home`),
  silent on failure, sent only by the server process (asgi), never by
  manage.py/tests/celery.

### Key settings / env (core/settings.py)

DEBUG (env, default off), SECRET_KEY (env; dev-only fallback, else
ImproperlyConfigured), ALLOWED_HOSTS / CORS (env-overridable, defaults open
with recorded WHY), DATABASE via env, FIELD_ENCRYPTION_KEY (Fernet for every
stored secret), INTERNAL_API_KEY, NEXUS_AI_URL, SUPABASE_URL + SUPABASE_ANON_KEY,
NEURALOPS_SERVER_URL, NEURALOPS_PORTAL_URL, NEURALOPS_PHONE_HOME_URL,
LOCAL_LOGIN_ENABLED, GATEWAY_ENABLED, GATEWAY_ASK_TIMEOUT_SECONDS=180,
PROJECTS_ROOT, MODEL_PRICES_URL, MEDIA_ROOT, LOG_DIR/LOG_LEVEL, CELERY_*
(queue "neuralops", DatabaseScheduler, task time limit 35min) and
CELERY_BEAT_SCHEDULE: refresh-model-prices-daily, expire-paused-runs-hourly,
expire-waiting-checkpoints-hourly.

### Requirements (docker/dev/requirements.txt) — Python 3.11

Deliberately UNPINNED in dev (floating): Django>=5.2, django-ninja,
pydantic>=2, psycopg[binary], dj-database-url, PyJWT, cryptography,
passlib[bcrypt], django-guardian, django-cors-headers, httpx,
centrifuge-python, celery[redis], redis, django-celery-beat, pillow,
markdown + Pygments (OPTIONAL at runtime — files.py degrades), python-dotenv,
django-extensions, rich, ipython, gunicorn, uvicorn, boto3, authlib.

The EXACT versions live in the running container; capture them any time with:
`docker exec neuralops-nucleus-dev /opt/venv/nucleus-env/bin/pip freeze`.
**Step 8's production image must freeze this list** (a lock file like the
engine's) and the pins get recorded in this document then — bump the
document version when that happens.

### Nucleus test files (457 total)

`authn/tests.py` + `authn/tests_step4.py` (login/setup/local, 14) ·
`chat/tests.py` (mentions, sessions, nudges, cards, search, relay) ·
`workspace/tests.py` + `tests_files.py` (viewer, 11) + `tests_step6.py`
(configure fence, tool lists, phone-home, 10) · `intelligence/tests.py`
(OAuth client, utility model, routines, recall, catalogs, model check) +
`tests_usage.py` + `tests_oauth_dyn.py` (dynamic registration/PKCE/relay, 9) ·
`scheduling/tests.py` (schedules, hooks, runbooks) + `tests_chains.py`
(supervisor/redo/checkpoints/gateway chain tools/template, 15) ·
`gateway/tests.py` (tokens, the MCP door, the tools, 12) ·
`internal/tests.py` · `nucleus/tests.py`.

---

## 5. nexus-ai — the map

FastAPI + pydantic-ai, Python 3.13. `fastapi_app/` (HTTP skin) and
`ai_engine/` (the brain; imports nothing of fastapi_app except
`contracts/`). Plan + trials in `docs/NEXUS-AI-REVAMP.md`; wire names are kept
EXACTLY as 0.8.0's so nucleus keeps working.

- **`fastapi_app/contracts/trigger.py`** — THE wire contract. TriggerJob in:
  job_id, msg_id (pre-made reply id), persona_id, topic_id, user_message_id,
  message, company/project/user ids, topic_tools + topic_tool_clearances,
  `resume` (ResumeBlock: verbatim state + approvals + answers + model role),
  context_sources, output_type, `preflight`, `approved_plan`,
  **`interactive`** (live: ask/nudge gating — unattended runs never get the
  ask_user tool), routine_id (ignored — routines are nucleus-side),
  step_context (the runbook block), delegation_depth. AgentEvent out:
  message_start/delta/done/error, keepalive, approval_requested,
  message_paused, tool_call_start/end, deep_escalation, retrieval refs.
- **`fastapi_app/routers/`** — `trigger.py` (POST /api/v1/trigger/, SSE),
  `embed.py`, `models.py` (model check), `search.py` (POST
  /api/v1/search/messages/ — the semantic ranking nucleus's chat search and
  the gateway call), `mcp_tools.py` (POST /api/v1/mcp/tools/ {url,
  bearer_token?} → [{name, one_line, read_only}]; any dial failure = one 502
  with the reason).
- **`ai_engine/core/`** — ai_system (the run loop), nucleus_client (pulls
  persona/history/context from nucleus's internal API), specs, config,
  billing, turn_rules (step_context + approved_plan prompt sections; prompt
  cache rule: stable sections first).
- **`ai_engine/pydantic_ai_system/`** — agent_builder, model_factory,
  reply_generator, escalation (router → deep model), message_converter,
  memory_pass, event_mapper, usage_reader, and **`tools/`**: toolset_builder
  (one auth header per MCP server: oauth2 → user token, static →
  client_secret — the recorded one-header limit), approval_policy +
  approval_gate (read/write by the server's own readOnlyHint; unlabeled =
  write = asks), ask_user (external toolset, INTERACTIVE runs only),
  call_persona (delegation, depth 1), nudge_gate, registry.
- **`ai_engine/context/`** — context_builder, history_policy, budget.
- **`ai_engine/output_types/`** — classifier/resolver/markers/recovery for
  text/code/chart/table/diagram/form/html/terminal.
- **`ai_engine/vector_db/`** — txtai + pgvector store, fastembed embedder,
  chunking, reembed.
- **MCP client facts (probed live, mcp 2.x — do not re-guess):**
  `from mcp.client.streamable_http import streamable_http_client` — signature
  `(url, *, http_client: httpx2.AsyncClient | None, terminate_on_close,
  max_sse_event_size)`, yields a `(read_stream, write_stream)` 2-tuple;
  headers/auth travel on a pre-built `httpx2.AsyncClient`;
  `from mcp import ClientSession`; the authlib/mcp world aliases httpx as
  `httpx2` in places. Fake server for tests:
  `mcp.server.mcpserver.MCPServer`, `ToolAnnotations(readOnlyHint=True)`.
- **Requirements (PINNED before any code was written — NEXUS-AI-REVAMP §1.5;
  `requirements.lock` holds the full resolved set Docker installs; Python
  3.13):**
  `pydantic-ai-slim[openai,anthropic,google,mcp]==2.55.0` ·
  `pydantic-ai-harness==0.55.0` · `pydantic==2.14.0` ·
  `fastapi[standard]==0.143.0` · `starlette==1.7.0` · `uvicorn==0.54.0` ·
  `httpx==0.28.1` · `genai-prices==0.1.10` · `Jinja2==3.1.6` ·
  `txtai==9.14.0` · `fastembed==0.9.0` · `sqlalchemy==2.1.4` ·
  `psycopg2-binary==2.9.13` · `pgvector==0.5.1` (python pkg; the production
  DB image planned is `pgvector/pgvector:0.8.7-pg17`). Docker note: install
  CPU torch FIRST (`pip install torch --index-url
  https://download.pytorch.org/whl/cpu`) or txtai pulls ~6GB of CUDA wheels.
  Never bump a pin casually — these were chosen by trial (the doc records
  the trials); a bump is its own discussed, tested change.
- **Engine tests (`tests/`):** fakes (fake_nucleus, fake_provider, fake_mcp) +
  test_acceptance, approvals, ask_user, budget, cost, delegation,
  dependencies, discovery, embed_endpoints, fallbacks, history, mcp_dial,
  model_check, nudges_memory, output_types, retrieval, router,
  search_and_mcp_tools, tools, turn_rules, vector_db (the 20 skips in the
  debug container).

---

## 6. Security constraints — NEVER break these

- Secrets live in `neuralops/secrets.env`. On an EXISTING install you may
  APPEND a line (e.g. SECRET_KEY); **NEVER re-run init-secrets** — it would
  replace the live POSTGRES_PASSWORD and kill the database connection.
- The dev POSTGRES_PASSWORD on the owner's box is a real generated secret —
  don't echo it beyond commands that need it.
- Never log a secret, token or key in code. MCPServerOut returns oauth_config
  (non-secret) but secrets/tokens only ever live Fernet-encrypted and go only
  to the engine's internal API.
- The vendor OAuth client SECRET never ships in any image or catalog — only
  the public client_id; secret-requiring exchanges belong to the portal relay.
- Phone-home sends ONLY `{install_token, event, total_tokens}` — nothing else
  ever leaves a customer's server. One number, total, all-time.
- Gateway tokens: value shown exactly once at mint; stored sha256 only.
- .pyc distribution (Step 8) hides source from casual eyes but is NOT
  encryption — never claim otherwise; the real protections are the portal
  identity anchor and phone-home.

---

## 7. Hard-won lessons (cost real debugging — don't relearn)

1. **Postgres migrations:** AddField(db_index=True) + a RunPython backfill on
   the same table in ONE migration fails ("pending trigger events"). Schema
   and data are SEPARATE migrations (see 0034 vs 0035).
2. **`--noinput` on every test run** — a stale test DB otherwise EOFErrors on
   the confirm prompt.
3. **PermissionChecker.can() raises on unknown right codes** — anything in
   row_rules/fences/background paths fails CLOSED via try/except ValueError
   (the Step 6 configure-fence bug: an un-reseeded server crashed every topic
   list).
4. **Don't guess APIs — probe.** The mcp 2.x import spelling was wrong twice
   until probed live in the container.
5. **The engine container is `nexus-ai-debug`.** Vector tests skip there by
   design.
6. **Celery runbook/chain runs are claim-guarded** (exactly one UPDATE moves
   the status); every exit of _drive must end the run row or it spins
   "running" forever; a long run must never hold a beat-fired slot (hand off
   with .delay).
7. **django signing payloads are readable without the key** (base64) — that is
   a FEATURE the OAuth relay depends on, and a reason never to put secrets in
   signed state.
8. **File-editing quirk (assistant-side):** the node3 edit tool fails on
   anchors containing long `────` divider lines (dash-count mismatch) — anchor
   on body text instead.
9. **ninja + Pydantic:** `model_config` is a reserved field name; use
   `Query(alias="as")` for reserved words; sync auth classes work on async
   operations; HttpError(400, msg) renders `{"detail": msg}`; a bare
   `payload: dict` on a PUT is read as a QUERY param — bodies need a real
   Schema class (the Step 3 EmbedderIn bug).
10. **One trigger road.** Every AI reply — mention, schedule, chain step,
    supervisor review, gateway ask — goes through
    `chat/services.trigger_ai_response_async`. Never build a second road.
    Same spirit: every call TO the engine goes through NexusAIClient.
11. **asyncio locks don't cross event loops** — the relay's queue-per-topic
    lock is kept PER EVENT LOOP (`_lock_for`), because async_to_sync callers
    (Celery) open a fresh loop per call and a reused asyncio.Lock raises.
12. **Django aggregates:** an alias must not reuse a column name
    (`cost=Sum("cost")` made a later `cost__isnull` filter hit the aggregate
    — FieldError); a 6-dp Decimal column returns "2.500000", so compare
    prices as Decimals, not strings.
13. **Step 0's kill list is law:** fifteen zero-reference tables, the swarm
    road, chat's old self-calling tasks and the terminal/browser panes were
    deleted WITH recorded proof — don't reintroduce them. `.step0-removed/`
    holds the retired files until the owner deletes it. ChromaDB services +
    CHROMA_* env serve only the LEGACY engine and are removed at Step 8's
    switch-over.

---

## 8. Current status (2026-10-15)

**CLOSED and owner-verified:** Steps 0–7 of `docs/NUCLEUS-REVAMP.md` — Step 4
login + posture (400 tests), Step 5 file viewer (411), Step 6 front doors:
gateway + tokens (A, 423), configure topic + stored tool lists + phone-home
(B, 433), OAuth roads (C, 442), Step 7 chains (457). Migrations through 0036;
49 rights; engine 90 passed / 20 skipped (debug container).

**Remaining, in order:**
- **Step 8** — switch-over (point the stack at the new engine, retire
  nexus-ai-legacy; first: run the engine's vector/search tests on the
  vector-enabled setup, add the engine's extra-headers server config so
  personas can use the gateway's no-token internal road, swap dev postgres →
  pgvector image) and distribution (ONE app image, nexus-ai + nucleus +
  centrifugo by command:, compiled .pyc only, init-secrets generates
  SECRET_KEY, owner claims via the portal code flow).
- **Portal-side (specced in NUCLEUS-REVAMP, not server code):** the claim
  page, the phone-home edge function (contract in core/phone_home.py's
  docstring), the OAuth relay (v1 pure forwarder contract in the Step 6C
  block), the three vendor "NeuralOps" app registrations.
- **Frontend:** everything in FRONTEND-REVAMP.md §2 — the backend already
  speaks every contract there.
- **Standing small items:** engine item 28 (vision), stdio-MCP dialing (tool
  lists for stdio servers), the owner may delete `.step0-removed/`.

**For any new change:** read the relevant step's rulings in NUCLEUS-REVAMP.md
first — the reasoning behind every structure above is written there, and new
work must not quietly contradict a recorded ruling without the owner re-ruling.
