# NeuralOps — what is still missing

**Started 2026-10-19 (owner's ask: "add a document what is missing, we will
run it later").** Plain language. Each item says WHAT is missing, WHERE the
gap is, and roughly HOW BIG the job is. When an item is built, move its line
to the matching BUILT block in FRONTEND-REVAMP.md / NUCLEUS-REVAMP.md and
strike it here with the date.

---

## ROADMAP TO RELEASE (consolidated 2026-10-22, owner + Claude)

**Stage 1 — finish the acceptance pass (now).** The live list is in
TEST-CASES.md §Progress: suites (engine 117 / frontend 1143), seed push +
TC-09a, default-router @Plain test, fallback (broken key) or defer, fresh
web_search + web_fetch + Web approval knob, TC-12 shell guard, external MCP
tiles TC-13/14, chains, team/invites, recall-pane inspection, gateway, UI
sweep, TC-38 embedder check. Plus the two pending git commits.

**Stage 2 — fix round. ~~REMOVALS~~ BUILT + VERIFIED 2026-10-22 21:49
(suites green at the new targets; three test-only stragglers fixed in the
first run — record in FRONTEND-REVAMP §2k).**
The removals the owner ruled 2026-10-22 15:50 are DONE in both repos:
DELIVERABLES (model, routes, schemas, Keep button, keep-dialog, pane, API
lib, hooks, 6 nucleus + 11 frontend tests) and RECALL (RecallEntry model,
recall API + internal route, Persona.recall_enabled everywhere, the engine's
recall kind + embed endpoints, the pane, the "Remembered N things" chip and
the whole `recalled` wire field, 5 nucleus + 1 engine + 10 frontend tests).
Migrations: nucleus **0042_remove_recall_and_deliverables** (drops both
tables + the persona flag, ROWS INCLUDED) and authn
**0007_recall_deliverable_rights_cleanup** (drops recall.manage +
deliverable.manage rights; registry 49 → 47). Removed code is parked in
nucleus `.step0-removed/` and web `_attic/removed-panes/`. Also ridden in
this round (both ruled): viewers may POST (the composer shows for everyone;
only persona calls are refused — the server already behaved this way) and
the supervisor verdict prompt got the pass-unless-broken bias (style is
never a defect; REDO needs a named, fixable problem). New suite targets:
nucleus **464**, engine **117 passed / 5 skipped**, frontend **121 files /
1122 tests**. This also VOIDS the recall-writer half of the memory-pass
hardening entry (parts 2/5 — no pane, no writer needed); parts 1 and 3
(don't store tool transcripts; retrieval text never poses as this turn's
output) still stand. Remaining Stage 2: the owner's comments file keyed by
TC id, if any comments come.

**Stage 3 — release chores.** Rotate the exposed OpenAI/Anthropic keys
(if not already done for the fresh start); Supabase cleanups (legacy
device-verify function, test-install-1 phone_home_events row); regenerate
engine requirements.lock at next image build (7c); `seed_catalog
--regenerate` + commit as the release's catalog snapshot.

**Stage 4 — post-release build queue (details in "Post-test build queue"
below). SCHEDULE AGREED 2026-10-23 evening (owner: "i need these things to
be done asap"; each item ships as its own point release when done, the
owner verifying daily):**
1. **Week of Oct 26–30 → 1.1.0:** Chains rework v2, all remaining 5 parts
   (rename, query input, @ChainName invocation, model-only steps, role
   labels — supervisor bias already shipped in 1.0.0).
2. **Week of Nov 2–6 → 1.2.0:** Connector tiles with icons (owner's 8-
   service list; OAuth2 flow exists) + MCP suggest-attach option 2 +
   FREE-LLM ONBOARDING parts 1–2 (catalog presets + configure-channel
   helper — full entry below).
3. **Week of Nov 9–13 → 1.3.0:** AI audit log (full reply anatomy +
   "investigate with a model") + backup & restore (one-command dump, DB +
   media, secrets.env excluded; restore onto a fresh install).
4. **Week of Nov 16–20 → 1.4.0:** Setup copilot admin tools (the owner's
   11-tool gateway list) + the secure key card + free-LLM one-click
   connects + file viewer pane (security ruling first).

Still parked (unchanged): local login UI, gateway mint-for-others,
delegation/tool_access/approval_scope toggles, portal guess-brake,
cached-tokens column on the usage rollups, usage by-kind split UI.

---

## 1. Persona seats the UI cannot set (found 2026-10-19, walkthrough)

**BUILT (2026-10-19, same night, straight after the ruling):** PersonaIn/
PatchIn/Out carry router_model_config_id + deep_model_config_id (+
clear_router/clear_deep; refs on Out); services resolve/validate/set both
seats (seat ≠ standard enforced, attach-to-project enforced); both persona
dialogs show Router + Deep pickers in the ruled order (Model → Router →
Deep → Fallbacks → Advisor) with attach-&-use, inline register per seat,
and primary-takeover clearing; cards chip "router · X" / "deep · X".
Tests: nucleus PersonaSeatTests (7) + 4 new frontend tests. NO migration
(the FKs existed).

**DEFAULT ROUTER — RULED PROJECT-WIDE (owner, 2026-10-19 23:43), BUILT
2026-10-21 (owner said "make all missing changes"; UI home picked by Claude:
the PROJECT OVERVIEW PANE — owner may move it to the configure topic).**
What was built:
- `Project.default_router_model` FK + migration **0039_project_default_router**;
- project API: ProjectOut ships `default_router_model {id, name}` (a retired
  model reads as none); PATCH project takes `default_router_model_id` /
  `clear_default_router` under project.update — the model must be active,
  this company's and ATTACHED to the project (update_project validates);
- `internal/api.py`: an EMPTY persona router seat fills from the PROJECT
  default; the persona's own seat wins; a default equal to the persona's
  STANDARD model is skipped (screening with itself saves nothing); the
  dormant CompanyAIConfig.default_router_model is no longer read at all
  (tests_step3 pins all four rules);
- UI: "Default router" section on the project overview pane — one select of
  the project's attached models, saved on change, [clear] = "No default
  router"; read-only sentence without project.update; too-old-server note;
- tests: nucleus ProjectDefaultRouterTests (workspace) + the reworked
  tests_step3 case; frontend +3 pane tests.
Still parked: delegation / tool_access / approval_scope.

**SMART ROUTER — RULED (owner, 2026-10-20 17:40: "no round robin, the
router will select … based on pros and cons of every model"), BUILT
2026-10-21 (all three repos; suites pending owner verify).** The deep seat
is a BENCH (0..N models, ordered) and the ROUTER picks the hand-over target
by each model's routing_notes. What was built:
- NUCLEUS: `PersonaDeepModel` bench table (like PersonaFallbackModel,
  ordered, first = default pick) + migration **0038_deep_bench** (creates
  the table AND seeds it from any single deep seat already set, so nothing
  configured is lost). `Persona.deep_model` FK stays as a LEGACY MIRROR of
  the bench's first entry (services keep it synced) so an older engine
  image keeps escalating. PersonaIn/PatchIn: `deep_model_config_ids` (list,
  [] clears on patch); the old `deep_model_config_id` + `clear_deep` still
  work (a one-item bench / an empty one) so old callers don't 400.
  PersonaOut + PersonaInternal ship `deep_models` (bench, in order) AND
  `deep_model` (= first). Wiring rules per bench member (≠ standard, same
  company, attached to project); delete/detach guards now also cover the
  ROUTER seat and the bench (they only covered model/advisor/fallbacks).
  PersonaSeatTests 7 → 10.
- ENGINE: bench models ride PersonaSpec.models as multiple DEEP entries
  (first = default — every existing road untouched); `models_for(role)` on
  PersonaSpec; `Escalate.target_model`; `router_instructions(bench)` lists
  a 2+ bench with each model's notes (1 or 0 → the plain text);
  `pick_deep_model()` matches name or model_id case-insensitively, falls
  back to the bench's first; ai_system runs the deep turn ON THE PICK
  (generator `primary=` override; budget + context_window follow the pick);
  an older nucleus's single deep_model maps to a one-item bench
  (nucleus_client). Tests r7/r8/r9 (113 → 116 passed).
- FRONTEND: DeepBenchPicker (ordered list like fallbacks, no cap, first
  row chips "default pick"); both persona dialogs swap the single Deep
  picker for it (order stays Model → Router → Deep → Fallbacks → Advisor);
  payloads send `deep_model_config_ids` (never the legacy single field);
  edit diffs positionally, [] clears; attach-&-use covers every bench
  model; cards chip `deep · X` for one, `deep bench · N` for more; the
  model dialogs' strengths field landed with 7b. Tests: 4 reworked + 3 new
  (1128 → 1131).
- Standard stays SINGLE and required, as assumed (owner did not veto).
- Considered and DECLINED (same exchange): round-robin / random multi-seat.
- VERIFY (owner): see FRONTEND-REVAMP §2g.


The database and the engine are READY for all of these (Step 3 built them,
the engine tests prove them) — but the public persona API (PersonaIn/Out)
and the builder dialogs never expose them, so nothing can set them:

- **Router seat** (`Persona.router_model`) — a cheap model that screens each
  message: answers trivial ones itself, passes the rest on. Falls back to
  `CompanyAIConfig.default_router_model` — which ALSO has no public API
  field (CompanyAIConfigIn lacks it), so the company default is equally
  unreachable.
- **Deep seat** (`Persona.deep_model`) — the heavyweight the router (or the
  standard model) hands a hard question to. Without a settable deep seat the
  whole escalation road (deep_escalation event, "Handed to <model>" note,
  already rendered by the chat since chunk 2) stays dormant.
- **Delegation** (`Persona.delegation_enabled`) — the supervisor checkbox:
  gives the persona `call_persona` (one-shot, depth 1). Engine: built,
  billed, tested (test_delegation). No API field, no checkbox.
- **Tool mounting + approval scope** (`Persona.tool_access` all|selected,
  `Persona.approval_scope` topic|requester_only) — stored, shipped on the
  internal API, enforced; never settable from outside.

**RULED (owner, 2026-10-19 23:33): road A — build the per-persona seats**
("actually squence is to have router, standard, deep, cheaper, fallback,
advisor etc … why dont we first add it" — his "cheaper" IS the router).
This supersedes the earlier "i dont know". Scope of the build: expose
router_model_config_id + deep_model_config_id on PersonaIn/PatchIn/Out (the
Django FKs already exist — NO migration) + Router/Deep pickers in both
persona dialogs with the seat rules below + CompanyAIConfigIn gains
default_router_model (fills an EMPTY router seat server-wide). Engine:
already built and tested — nothing to change. Delegation / tool_access /
approval_scope stay parked (not part of this ruling). NEXT BUILD SESSION,
first in line, ahead of 7b. The two roads, for the record:

- **A. Per-persona seats** — the table below; full control, heavier builder.
- **B. Server-side simplicity** — personas keep only Model/Advisor/Fallbacks
  as today; router and deep live ONLY as company-wide defaults (one setting,
  every persona benefits), or are dropped entirely. The engine supports both
  roads already — this is purely a product decision.

If road A is picked, the sketch:
One "Model seats" picture, in plain words:

| Seat | Required? | What it does |
|---|---|---|
| **Standard** | ALWAYS (it is today's "Model") | answers every normal message |
| **Router** | optional | a cheap screener: answers trivial messages itself, passes the rest to Standard, may escalate |
| **Deep** | optional | the heavyweight a hard question is handed to ("Handed to <model>" in chat) |
| Advisor | optional (already in the UI) | a second opinion Standard consults mid-reply — never takes over |
| Fallbacks 0..3 | optional (already in the UI) | answer only when Standard FAILS |

Seat rules to enforce in the builder (matching what the engine already does):
- Standard is always required — the other seats hang off it.
- Router alone is fine (screen + pass to Standard, no escalation target — hard
  questions just stay on Standard).
- Deep alone is fine too: with no Router, the STANDARD model itself decides to
  hand over (engine test r5) — but the owner's expectation reads naturally as
  "a deep seat usually comes with a router + standard", so the builder should
  HINT that pairing (not block the lone-deep case the engine supports).
- A seat must differ from Standard (same rule the advisor already has).

**The job:** one backend change (PersonaIn/PatchIn/Out gains
router/deep model ids + clear flags, services validation with the same
project-attachment rules as the advisor; CompanyAIConfigIn gains
default_router_model; + nucleus tests) and one frontend change (Router and
Deep ModelPicker slots in a "Model seats" section + the delegation /
tool-access / approval-scope toggles; + tests). Medium.

## 2. MCP server screen — stored tool list + Refresh (FRONTEND-REVAMP §2.7)

**BUILT (2026-10-21, frontend half — nucleus was already built).**
MCPServer type gained `tools` + `refreshMcpTools()`; the card of every
external HTTP/SSE server sums its stored list in the meta line ("3 tools ·
1 read / 2 write", or "no stored tools") with a **Refresh tools** button
(mcp_server.update) whose failed dial shows the 502 reason VERBATIM beside
it; the edit dialog gained a read-only **Tools** section listing each stored
tool with its read / write / write-(unlabeled) badge. Internal rows and
stdio stay untouched (no stored lists yet). +4 frontend tests.

## 3. File viewer (FRONTEND-REVAMP §2.4)

Nucleus half BUILT (browse/download/view endpoints with the sandbox rules).
Frontend DEFERRED by the owner ("if not now, later"). **The job:** one new
pane/screen + error wording for 404/400/409/413/415; medium.

## 4. Embedder setting + rebuild banner (FRONTEND-REVAMP §2.11) — TO VERIFY

Nucleus half built (GET/PUT /projects/{id}/embedder/, reindex_status).
Whether the frontend project-settings row and the "memory is being rebuilt"
banner exist has NOT been verified — check before building. Small-medium.

## 5. Local (offline) login UI — PARKED (owner, 2026-10-18)

Backend endpoints exist and wait (/auth/local/signin, set-password,
reset-password). Supabase stays the only login road in the UI until the
owner unparks this.

## 6. Gateway: mint a token FOR someone else

The server supports POST /gateway/tokens/ with user_id (company-level
holders only). The new Gateway page mints for yourself only. Small
frontend addition (a member picker) when wanted.

## 7. Portal / distribution track

- **device-claim guess-brake** (recorded TODO): ~5 wrong codes per account
  per 10 min → wait. Needs an index.ts change + owner redeploy. Small.
- **OAuth relay + vendor "NeuralOps" app registrations** — the catalog's
  oauth_preset client_ids are empty until the vendor apps exist; until then
  the "Connect with NeuralOps" button rightly stays hidden.
- **Step 8 distribution half** — rebuild the PRODUCTION profile around the
  unified image's new engine (nexus-ai-new semantics, chromadb retirement),
  publish the image. Large; its own step.

## 7b. Max tokens AND temperature move to the MODEL — **BUILT 2026-10-20**
(owner, 2026-10-19: "i think the road B" … "i think max tokens, and
temperature should be in model"; release plan #2)

**BUILT:** `ModelConfig.max_output_tokens` (16000) + `.temperature` (0.7) +
`.routing_notes` (the smart router's strengths line, carried in the same
migration) — **migration 0037_model_generation**, no backfill on purpose
(several personas can share a config, so any copy would be a guess).
ModelConfigIn/PatchIn/Out carry all three; `_model_config_out` returns them;
PersonaIn/PatchIn still ACCEPT temperature/max_tokens so old callers don't
400, and services pop them unread. Internal API: ModelInternal carries them,
so the engine budgets and generates PER CANDIDATE. Engine: ModelSpec gained
the fields (defaults keep an older nucleus working — the persona's legacy
numbers stand in, see nucleus_client.model_spec_from); agent_builder reads
`spec.temperature` / `spec.max_output_tokens`; reply_generator and ai_system
budget from the candidate's own cap. Frontend: both MODEL dialogs gained a
Generation section (Max reply tokens / Temperature / Strengths note), the
model card shows "reply Nk", and BOTH persona dialogs LOST temperature and
max tokens (Generation keeps Max steps + Proposes first + Recall). Tests: 1
engine file (2 cases incl. the older-nucleus fallback) + 2 frontend cases +
updated persona cases. Persona.temperature/max_tokens COLUMNS stay for now
(dropping them is a later cleanup; nothing reads them).

Today both sit on the persona (max_tokens default just raised to 16000).
The ruling: they are properties of the MODEL — each model has its own
output ceiling and its own sensible temperature. The final split:
**the model card owns HOW it generates (max output tokens, temperature);
the persona owns WHAT it is and does (prompt, tools, max steps,
propose-first, recall).** Known trade, accepted: two personas sharing one
registered model share its temperature — wanting two temperatures means
registering the model twice (same key, two cards).

The build, when we run it:
- **nucleus:** `ModelConfig.max_output_tokens` (int, default 16000) and
  `ModelConfig.temperature` (float, default 0.7) + ONE migration; expose in
  ModelConfigIn/Out and both model dialogs (near context window);
  PersonaInternal's ModelSpec entries carry each model's own numbers;
  PersonaIn.max_tokens/temperature become optional/ignored (kept so old
  callers don't 400); persona create/edit dialogs lose both fields
  (Generation keeps Max steps + Proposes before acting + Recall).
- **engine:** budget math + run settings read the ANSWERING model's
  max_output_tokens and temperature (today: persona-level) — per candidate,
  so a fallback with a smaller ceiling gets its own right numbers.
- **tests:** nucleus persona/model API suites, engine budget tests, frontend
  personas-tab + models-tab suites.
- Size: a solid evening. Not started — tonight's walkthrough runs on the
  current shape (persona fields, max_tokens default 16000), which works fine.

## 7c. Engine image: regenerate requirements.lock with the web-fetch extra
(found 2026-10-19, owner's first live persona)

A persona with the web_fetch capability crashed at toolset build ("No module
named 'bs4'") — the image's pydantic-ai-slim install lacked the `web-fetch`
extra (bs4 + markdownify). FIXED for tonight by pip-installing it into the
RUNNING nexus-ai-new container (lost if the container is ever recreated),
and requirements.txt now carries the extra. STILL TO DO: regenerate
requirements.lock from the updated requirements.txt (never hand-edit —
lesson 14) and rebuild the image — fold into the next image build.

## 8. Owner's own list (no code)

- Supabase dashboard: delete the legacy `device-verify` function; delete the
  `test-install-1` row in phone_home_events.
- If the nexus-ai-new container is ever RECREATED before the image rebuild
  (7c): re-run `docker exec neuralops-nexus-ai-new
  /opt/venv/nexus-ai-env/bin/pip install "pydantic-ai-slim[web-fetch]"`.
- Rotate the OpenAI/Anthropic keys that appeared in earlier terminal pastes.
- Git commits in BOTH repos — **DONE 2026-10-21 17:11**: backend 581d21b
  (step8-switchover), frontend 79bcef4 (noamanfaisal) — the whole revamp
  through the spend limit, suites 469/116/1140 all green at commit time.

## 9. Later / nice-to-have

- **Cached tokens on the Usage page — BUILT 2026-10-20** (release plan #1):
  `cached_tokens` on _money + every breakdown row; by_kind split on the
  project/company rollups (usage_api.py); Usage page shows a "From cache"
  stat with its share, a Cached column, and a "By kind of work" table in
  plain words (Chat replies / Router screening / Memory passes /
  Embeddings); older servers without the fields render clean. Tests: one
  nucleus (rides UsageReadApiTests) + one frontend. Original note kept
  below for history.
  (owner noticed 2026-10-19; scope CORRECTED after reading the code): the backend already has it ALL — the
  engine captures cache read/write per call, nucleus stores the columns
  (cache_read_tokens, cache_write_5m/1h, uncached_input_tokens,
  reasoning_tokens) AND prices cache reads at the cached rate (pricing.py).
  Only the LAST MILE is missing: the usage rollup endpoints (topic/project/
  company) sum just input/output, so the frontend has nothing to show.
  Build: add cache sums to the three rollups' _money shape + a Cached column
  (or "N% from cache" note) on the Usage page. Small; no migration.
  ALSO (owner's usage question, 2026-10-20): a by-KIND split on the Usage
  page — the rows already store kind (chat_reply/router/memory) and seat
  (role), the rollups just don't group by it. Interesting once routers are
  live ("what does the screener cost vs save?"). Small; same endpoints.
- **Default project capabilities — RULED (owner, 2026-10-21 16:25): KEEP ALL
  FOUR** (filesystem, shell, web_search, web_fetch). Today's behavior stands
  — nothing to build; per-persona unticking and the MCP screen's capability
  editing stay the control points. CLOSED.
- **Spend limits — RULED (owner, 2026-10-21 16:25: per-PROJECT monthly cap,
  BLOCK at the cap), BUILT the same hour.** `Project.spend_limit_monthly`
  (Decimal USD, null = no limit) + migration **0040_spend_limit**; the sum is
  the project's UsageRecord.cost for the CURRENT CALENDAR month — ESTIMATED
  by design, unpriced rows count 0 (workspace/services.py spend_this_month /
  spend_limit_reached). Enforced in chat/api.py _trigger_personas, the same
  road as the reindex lock: the human message still posts, the AI reply is
  refused with code "spend_limit" and a worded message naming ≈spent/cap.
  API: ProjectOut ships spend_limit_monthly + spent_this_month (detail
  route only; decimal STRINGS, money is never a float); PATCH project takes
  spend_limit_monthly / clear_spend_limit under project.update (validated:
  >0, ≤1,000,000). UI: "Monthly spend limit" section on the project
  overview pane — ≈spent aside, a dollar input, Save/Remove, estimates
  caveat spelled out. Tests: nucleus SpendLimitTests (+1 → 469), frontend
  +2 pane tests (→ 1140).
- **gpt-4o-mini showed "no price known"** (2026-10-19, first live run): the
  daily refresh_model_prices task should fill it from the litellm catalog.
  If it still shows after a day, investigate the catalog fetch/key matching.
- **Register-dialog defaults from the catalog DB — RULED (owner, 2026-10-21,
  during the from-zero test pass: "these default values must be fetched from
  db"), BUILT the same hour.** ModelPrice gained context_window +
  max_output_tokens (migration **0041_catalog_windows**), filled by the same
  daily litellm refresh that fills prices (rows with sizes but no prices are
  now kept too); GET /model-configs/defaults/ serves them to the register
  dialog, which prefills on id blur / provider change and never overwrites a
  hand-typed value; the frontend's hardcoded table (src/lib/model-context.ts)
  is now only the offline fallback. PLUS the owner's follow-up ruling the
  same evening: setup pushes DEFAULT DATA into the DB — `manage.py
  seed_catalog` loads the bundled snapshot (fills missing rows only, never
  downgrades the online refresh), `seed_catalog --regenerate` re-downloads
  the latest catalog from GitHub and rewrites the bundled file at release
  time (the file is committed, so it is versioned on GitHub with the code).
  Persona prompts / catalogues / templates already ship in code — no seed
  needed. Full detail + VERIFY block: FRONTEND-REVAMP §2j. Targets after
  this: nucleus 475 · frontend 1141 · migrations through 0041 (engine
  unchanged).

## Post-test build queue (owner, 2026-10-22 morning — build AFTER the
## acceptance pass; design details to be ruled when each starts)

- **MEMORY-PASS HARDENING — ~~REQUIRED BEFORE RELEASE~~ PARTS 1+3 BUILT
  2026-10-22 23:45 (the only parts that survived the Recall removal; 2/5
  voided, 4 fixed earlier).** Part 1: the memory pass never stores a
  shell/terminal transcript verbatim — prompt hard rules PLUS a code guard
  (_NEVER_RAW_TOOLS: a `raw` ruling on shell/run_command/terminal/
  execute_command downgrades to its summary or to nothing); trivia and
  anything that looks simulated is ruled skip. Part 3: the RETRIEVED prompt
  section now ends with a provenance rule — remembered text is never
  presentable as this turn's tool output and is named as memory when used.
  Tests: engine +m3 (transcript never raw; summary survives; non-shell raw
  untouched) and tr1 extended (provenance line reaches the model). Engine
  target moves 117 → **118** — VERIFIED by owner 2026-10-22 23:01: "118
  passed, 5 skipped". Original entry kept below for history:
  (promoted 2026-10-22 after the fabricated-terminal finding).** Three parts: (1) the pass must
  stop recording trivia and must NEVER store tool/terminal transcripts as
  facts — a fabricated transcript got stored and was replayed verbatim in
  its topic; (2) VISIBILITY: "Remembered N things" rows live only in the
  vector store with NO UI — the owner found the Recall pane empty while the
  chip counted away; either show memory-pass rows somewhere curatable or
  stop the chip implying they're inspectable; (3) retrieval-echo: text served
  from memory must not be presentable as THIS turn's tool output. Mitigating
  facts: memory rows are same-topic-scoped, so poison is contained to its
  topic (archiving the topic buries it). FOUND 2026-10-22 15:15 while the
  owner chased the empty pane, TWO MORE PARTS: (4) the "Remembered N things"
  chip was a MISWIRE — chat/relay.py published len(retrieved_sources) as the
  recall count, so every memory SEARCH claimed a memory WRITE (fixed same
  hour: relay publishes no count until real recording exists; nucleus suite
  must re-run — if a chat test asserted the old count, that test asserted the
  bug and gets fixed too); (5) RECALL HAS NO WRITER — storage, internal route
  (/internal/recall/), pane, editing all exist and are tested, but no persona
  tool or engine path ever records an entry; "remember this decision: we
  deploy on Fridays only" was acknowledged in words and stored nowhere. The
  hardening build adds the writer: a record_recall tool (or the memory pass
  writing decision/fact/preference entries) through the existing route, and
  the chip counts THOSE writes only.

- **AI audit log ("log for all chats").** Project owner/admin can open any AI
  reply and see the whole anatomy: the user's query, what retrieval fetched
  (vector DB hits — and graph DB once that exists), the exact prompt and
  history sent, the model's raw response, model/seat/lane, tokens and cost.
  Plus "investigate with a model": ask a model questions ABOUT the log from
  inside it. Foundations already exist: AIRequestLog rows, UsageRecord,
  retrieved_sources on message_done — the build is capturing the full prompt
  /retrieval payload per reply, a permission-gated API (owner/admin only —
  this is reading people's chats, needs its own right), and the viewer UI.
- **Connector tiles with icons.** The add-MCP screen shows ready-made tiles
  (icon + one click to configure) for: GitHub, Bitbucket, a graph-DB context
  MCP, Atlassian, AWS, Google, Vercel, draw.io/charts (owner's list, extended
  2026-10-22 19:45) — OAuth2 flow already built, the
  mcp_catalog already pre-fills dialogs; the build is catalog entries with
  icons + tile UI + per-service oauth_config defaults, each entry TESTED
  against the real service.
- **Backup & restore.** Owner's scope to confirm at build time (proposed:
  one command dumps DB + uploaded media; secrets.env stays out by the
  append-only rule; one command restores onto a fresh install).
- **File viewer pane (un-parked).** Browse project files with: download,
  upload, and "run as HTML server" (serve a folder/file as a live preview —
  security ruling needed: who may run it, same-origin isolation).
- **CHAINS REWORK — RULED (owner, 2026-10-22 18:39, after testing runbooks
  live).** Six parts:
  (1) RENAME: "chain" everywhere — UI, banners, docs (code may keep runbook
  internals).
  (2) STEP ACTOR — BOTH KINDS: a step is a PERSONA (full power: tools,
  approvals, identity — unchanged) OR a bare MODEL + prompt (text-only
  transform: no tools, no approvals; cheap). Design points to settle at
  build: who a model step posts as (proposal: the chain itself as sender,
  model named in metadata) and how its usage bills (no persona_id —
  proposal: kind=chat_reply with the chain/run id).
  (3) QUERY INPUT (the owner's best ask): a chain takes a QUERY at run time;
  it rides into step 1 as the task and every step can see it — chains become
  reusable workflows, not frozen scripts.
  (4) INVOCATION: @ChainName <query> in chat, allowed for project admin/
  owner; whether the Run button stays as a second door — owner no
  preference, decide at build (Claude leans keep).
  (5) ROLE LABEL per step, so banners read "step 2 of 4 — Reviewer".
  (6) SUPERVISOR BIAS: verdict prompt gets a pass-unless-broken rule — live
  test showed a self-reviewing supervisor REDO-ing materially fine work
  until the cap failed the run (same fix family as the router's keep-it
  bias). Also warn in the UI when the supervisor is also a step persona.
  Inline ad-hoc chains (@chain "@A @B" "query") SKIPPED for v1 — fragile;
  a saved chain + query gives the same power.
- **FREE-LLM ONBOARDING — RULED (owner, 2026-10-23 evening; full work
  order with hard rules lives in the owner's private project doc
  free-llm-onboarding-prompt — business/credits tracks stay OUT of this
  public repo).** Goal: "install NeuralOps, talk to a model in 2 minutes,
  for $0" — each user brings their own FREE-TIER key; NeuralOps never
  ships, shares or pays for a key. Four build parts:
  (1) **"Free to start" presets in the CATALOG** (seed_catalog data, not
  prompt text): one row per provider — GitHub Models (OpenAI-compatible,
  GitHub token), Google Gemini free tier, Groq, OpenRouter :free, Mistral,
  Cerebras, Ollama (local; no key — flagged as the private option) — each
  with provider type, API base, recommended model ids, the provider's
  key-page URL, a rate-limit note and a data-usage note. UI: tiles in
  /add-model with everything prefilled except the key. A dead free tier is
  fixed by a catalog refresh, never a prompt edit.
  (2) **Configure-channel HELPER persona**: walks a new user from zero to
  a working model — triage (cloud or local? which accounts exist?), exact
  per-provider key steps, honesty notes (rate limits; some free tiers may
  train on data; Ollama is the private path), then hands off to the
  prefilled /add-model dialog (and to part 3's tool once it exists). Its
  provider knowledge comes from the catalog presets, never hardcoded.
  (3) **register_model via the setup-copilot gateway tools + a SECURE KEY
  CARD** (first slice of the setup-copilot entry below): the tool
  PROPOSES; an approval card carries a write-only secret field — the key
  is typed ON THE CARD, verified with the provider (the Check path),
  stored encrypted, never echoed; message history records only "model X
  registered". A raw key must never travel through a chat message (chat
  lands in DB/history/memory). Rights: approver needs model management;
  card expiry follows the 24h rule.
  (4) **One-click connects**: "Connect OpenRouter" via OpenRouter's
  official OAuth PKCE (app obtains a user-scoped key on consent — reuses
  the MCP OAuth plumbing); GitHub Models via a GitHub OAuth app IF a
  non-PAT token proves out at build time, else the guided-PAT path stays.
  HARD RULES (none bend): no shared/baked key ever; no automated account
  registration or consent-clicking — the human clicks every consent and
  approves every card; keys never in chat; honest rate-limit/data-usage
  wording. Parts 1–2 build in the Nov 2–6 week; parts 3–4 ride the setup-
  copilot week.

- **MCP suggest-attach — RULED (owner, 2026-10-22 17:34: "option 2").** The
  persona may SEE the names + descriptions of the project's other MCP
  servers — never their tools, never a call — just enough to say "this
  project has X, which could answer this; someone with edit rights can
  attach it to me." Attach stays a HUMAN CLICK gated by the persona-edit
  right, once per persona+server; from the next reply the topic cache
  (layer 2) picks it up and the read-quiet/write-ask rules (layer 3) apply
  unchanged. The router points at the wall, never climbs it: no silent
  auto-attach, a crafted message must not be able to arm a persona. Found
  live: "what shopping tools do you have?" → "none" while Shopping (demo)
  sat one tick away. Build after the pass (Stage 4).
- **Setup copilot — ADMIN TOOLS ON THE GATEWAY (owner asked 2026-10-22: "ai
  can help me setting up models, mcps, users, personas" — NOT yet developed;
  the neuralops-mcp repo is only a shopping-tools demo).** CORRECTED after
  the live gateway test (2026-10-22 19:18): gateway tokens open ONLY the MCP
  endpoint (POST /api/v1/mcp/), not REST — by design, no master user. So the
  build is: EXTEND the gateway's tool list (gateway/api.py TOOL_DEFS +
  gateway/tools.py) with admin tools — register_model, check_model,
  create_persona, add_mcp_server, invite_user … — each permission-checked as
  the token's person, exactly like the dialogs. The same tools can then be
  mounted INSIDE for personas via the InternalActor door (X-NeuralOps-User
  carries the asking person; rights still theirs, writes still gated by
  approvals). One door, one rights rule, both worlds.
  THE OWNER'S TOOL LIST (ruled 2026-10-22 19:27, names normalized to the
  existing list_*/verb_* style):
  - models: list_models · create_model (runs the same pre-save provider check
    as the dialog) · update_model
  - personas: list_personas · create_persona · update_persona
  - users: list_users (invite_user later with the team build)
  - topics: list_topics (exists) · get_topic_messages (a topic's transcript,
    with a filter: AI replies only, or all messages) · create_topic ("add
    chat") · update_topic (rename/archive — "set_topics")
  Every one permission-checked as the calling person, same rights as the
  dialogs. NOTE for create_model/update_model: an api_key travels as a tool
  argument — never echoed back in results, never logged; results carry
  has_api_key only, like the REST API.

- MCP connector toggles ship WITH the bundled connectors (scope ruling: no
  dead switches) — MCP track.
- Edit dialog: gate Save behind a passed check the way Register now is?
  (Today: Edit checks on save when the reach changed; the explicit Check
  button exists. Owner to rule if Save should also lock.)
- gpt-5.x pricing rows in the price catalog — watch the Usage page's
  unpriced_rows (≥) on new models; the catalog refresh task may lag new ids.
