# NeuralOps Nexus — the test catalog

**Document version: 1.3 (2026-10-19).** Baselines: **nucleus 456 tests OK**,
**engine 110 passed / 0 skipped** (in `neuralops-nexus-ai-new`, since
Step 8a — the vector-db tests run for real against pgvector; a skip of a
BASELINE test is a regression. The 5 `live` tests showing as skipped in a
plain run is EXPECTED — they only run with `--real` + keys).

| Version | Date | What changed |
|---|---|---|
| 1.3 | 2026-10-19 | Terminal-only setup ruling: nucleus baseline 457 → **456** — SetupFlowTests rewritten (claim_install tested at service level; the removed /setup/start|poll roads pinned CLOSED by a new test; dead-portal endpoint test gone with the endpoint — that path now lives in create_owner, verified by hand) |
| 1.2 | 2026-10-17 | Added the REAL-model smoke suite (`test_real_smoke.py`, 5 tests, marker `live`): runs only with `--real` + keys in the environment; OUT of the 110 baseline; evidence in git-ignored REPORT-live.md |
| 1.1 | 2026-10-15 | Step 8a: engine baseline 90+20skip → **110/0** — the 20 vector tests run against `nexus_vectors` (pgvector); engine container renamed to `neuralops-nexus-ai-new` |
| 1.0 | 2026-10-15 | First catalog, at the close of Step 7 |

**The rules of this file:**
1. Every test here is a GUARANTEE the owner verified. Deleting or weakening a
   test = deleting a guarantee — it needs the owner's ruling, like a design
   change.
2. Every new test lands with a row/line here, in the same change. Bump the
   version.
3. Test names in this codebase are sentences on purpose
   (`test_the_run_parks_then_the_answer_resumes_it_with_the_answer_in_context`)
   — the name IS the description. This catalog describes each CLASS (one
   behavior area each); read the file for the sentence-level list, or dump it:

```
docker exec -w /nexus/nucleus neuralops-nucleus-dev sh -c "grep -rn 'class .*Tests\|def test_' --include='tests*.py' ." 
docker exec -w /nexus/ai neuralops-nexus-ai-new sh -c "grep -rn 'def test_' tests/"
```

**How to run** — see CHANGE-PROMPT.md §3 (always `--noinput` for nucleus).

**The real-model smoke suite (`tests/test_real_smoke.py`, marker `live`):**
NOT part of the baseline — it calls real providers and costs real cents.
Runs only with `--real` AND keys exported in the terminal (never in files):

```
export OPENAI_API_KEY=...   # and/or ANTHROPIC_API_KEY=...
docker exec -w /nexus/ai -e OPENAI_API_KEY -e ANTHROPIC_API_KEY neuralops-nexus-ai-new /opt/venv/nexus-ai-env/bin/python -m pytest tests/test_real_smoke.py --real -s
```

Five tests: one real streamed reply from each of TWO OpenAI models
(gpt-4o-mini and gpt-4o — one key covers all five; override with
OPENAI_TEST_MODEL / OPENAI_TEST_MODEL_2); a real tool round-trip
(grounded code word); the real ask/pause road; models/check with good and
garbage keys. Asserts check shape, prints show the real replies, and the
run writes `tests/REPORT-live.md` (git-ignored). A failure here points at
provider/network/key/model-id before the engine.

---

## 1. nexus-nucleus (Django test runner; 457 tests)

### authn/tests.py
Rights system fundamentals: the registry, role bundles, PermissionChecker
scope walking, row visibility (visible_projects/channels/topics and friends),
my-permissions payload (incl. the minimal-registry fixtures that caught the
Step 6 fail-closed fence bug), avatars (set/assign, missing pool warning),
invitation/acceptance roads.

### authn/tests_step4.py (14) — login and setup
- **Claim flow:** setup status on a fresh install; the code handed out;
  pending → first verified claim creates the owner WITH real seeded rights;
  the second claim gets 409; a dead portal answers 502 naming `create_owner`.
- **Local (offline) login:** set your own password (weak refused with
  Django's reasons); sign in offline and the HS256 token opens a real
  endpoint; wrong password vs ghost user answer identically; the brake (11th
  try in 5 min → 429); LOCAL_LOGIN_ENABLED=false kills even already-issued
  tokens; token expiry; admin reset needs company.local_password; persona
  (shadow) accounts refused.

### workspace/tests.py
Projects/channels/topics CRUD and visibility; InviteGrantsFixture (the base
fixture most suites build on: Acme, owner, sara, projects Alpha/Beta/Gamma,
seeded registry); invitation grants (whole project vs topic-scoped, the
never-granted project stays invisible); members/team; deliverables (keep,
versions v1/v2, conflict, permission gates); project brief; embedder
endpoints (`tests_embedder.py` section, 9: spec validation, the company-only
right, the 409 while a rebuild runs, lock/unlock, trigger fence refusal
code "reindexing").

### workspace/tests_files.py (11) — the file viewer (Step 5)
Browse order (folders first) and subfolders; viewer-vs-outsider 404;
no-folder 409; download streams exact bytes as attachment; dir/file kind
mix-ups 400; THE WALL: `..` and a symlink pointing out both refused; the
rendered markdown page is CSP-sandboxed; code view; 413 over the render cap;
415 binary.

### workspace/tests_step6.py (10) — configure topic, tool lists, phone-home
Every project born with the configure topic + the backfill; the fence holds
on EVERY road (lists, single topic, id sets) for exactly the four roles —
incl. a project-level Admin — and a direct topic invite does NOT pierce it;
tools refresh stores the mapped list, 403 for a Member, 502 carries the
dial's reason verbatim, internal rows never dialed; the engine payload
carries the stored list; phone-home sends exactly {install_token, event,
total_tokens} and is silent with no token / offline.

### chat/tests.py
Directive parsing (@mention/@session/output types/routines); the send path's
persona.mention gate (MentionRightFixture lives here); tool-activity events;
message serialisation extras (questions, used_tools, retrieved_sources);
PausedRelayTests + ToolApprovalDecisionTests — pause parks the job on
PausedRun, decisions are row-locked once-per-call, the resume fires only
when EVERY pending call is decided (the two-pending test); queue-per-topic
order (two triggers on one topic run in order); nudges (seen/leftovers);
stop; sessions; search (semantic ids → visibility filter → literal
fallback, incl. the engine-down fallback); Step 3 section (5): question
answer endpoint, pause expiry (24h deny/no-answer then resume), history
rows carry status.

### intelligence/tests.py
ClientOAuthTests — the paste-your-own OAuth road over the REAL code (only
the token exchange mocked): authorize URL params, state round-trip,
callback stores tokens, bad/unknown state refused, refresh_if_needed's
whole decision table, _store_token preserves a refresh_token the provider
omitted. UtilityModelTests (W17), PersonaGateTests (acts_after_approval),
ToolLevelsTests (auto/ask/off validation + worker payload), RoutineTests
(four built-ins seeded once, CRUD rights, built-ins editable never
deletable, worker payload with model+key), FallbackModelTests (order,
caps, wiring rules, delete guards, worker payload skips retired),
ModelCheckTests (the check button: right gates, categorised refusal
wording, stored-key reuse, 502/503 split), RecallTests (dedupe, caps,
attribution, embed/delete vector calls, rights), CatalogueTests (shape,
no secrets in the catalog, rights).

### intelligence/tests_usage.py (11) — the money tables (Step 1)
Pricing order (override → catalog → null-cost-still-counted) with exact
Decimal math; POST /internal/usage/ (401 without the key; priced rows;
live usage_totals pushed); the three read gates (topic participant /
usage.view_project / usage.view_company); "estimated" label everywhere.

### intelligence/tests_oauth_dyn.py (9) — the OAuth roads (Step 6C)
Dynamic registration fills client_id + endpoints and keeps a returned
secret ENCRYPTED; a fully pasted config makes zero network calls; no
registration endpoint → plain-words refusal → 502 through the API; the
Connect click auto-registers end to end and the URL carries
code_challenge + S256; portal_relay mode points redirect_uri at the portal
and server_url is readable from the state WITHOUT the key (decoded both
ways); the callback exchange carries the code_verifier from state;
oauth_preset exists for exactly github/atlassian/google-drive and carries
no secret.

### scheduling/tests.py
Schedules: create/update/delete rights (creator vs schedule.manage),
interval/crontab/clocked kinds, pause, fire road — creator is the actor,
re-checked (skips recorded when they lost rights or their account),
trigger_visible announcement, `interactive=False` asserted on every fire.
Hooks (W12): token URL fires a mention as the creator, rate limit (frozen
clock), size caps, 404/403/409/413 vocabulary. Runbooks (W6):
RunbookFixture + the faked-worker executor; definition validation (1–12
steps, persona/routine/prompt/output_type/on_failure); run rights
(runbook.run + persona.mention, new-topic road); the drive loop — step
results, retry once, skip carries past, stop between steps and mid-step,
the claim guard (a second delivery does nothing), every announce line.

### scheduling/tests_chains.py (15) — chains (Step 7)
Supervisor + redo_limit round-trip, clear_supervisor, bounds (0–2),
foreign supervisor refused; checkpoint step validation (question required,
no retry, unknown kind refused); a checkpoint chain refused at SCHEDULING
(400 "run it by hand") and at FIRE TIME after an edit; approvals let the
run finish with verdicts recorded and every call unattended
(interactive=False); REDO reruns the stage WITH the notes in the prompt;
exhausted REDO and FAIL fall to on_failure (stop fails the run with the
reviewer's reason; skip carries past, run finishes unclean); unclear
verdict stands; the park → 403 (viewer) → starter answers → 409 on the
second answer → resume with the answer in the next step's context —
end to end; expiry applies the checkpoint's own on_failure (stop fails,
skip re-enqueues); the hourly task only touches runs past the 24h window;
stop works while waiting; every new project is born with the step-less
"Draft and review" template which refuses to run; the gateway's
list_chains/run_chain/chain_status work as the person and a viewer may
look but not run.

### gateway/tests.py (12) — the MCP door (Step 6A)
Minting follows the four roles (incl. a project-level Admin; only
company-level mints FOR someone); admins see every token, members their
own, revoke rules; the wire shape (initialize echoes the protocol,
tools/list names all EIGHT tools, tools/call, notification → 202, unknown
method/tool); wrong, revoked and absent tokens 401; the internal road
(key + user header, rights as that person); GATEWAY_ENABLED=false → 403;
post_message respects visibility; ask_persona returns the reply and keeps
the rights fence; search_memory filtered by the caller's visible topics.

### internal/tests.py (+ the Step 3 section, 4)
The engine's private API: key gate; persona payload carries seats
(router resolved through the company default), flags, fallbacks with
keys, MCP secrets and tools; history rows carry status; recall write
road (404 across projects); pause storage.

### nucleus/tests.py
Model-level basics (soft delete, slugs, constraints).

### context (tested through chat/internal suites)
Context sources ride the embed payloads and the internal history/context
endpoints; no standalone file today.

---

## 2. nexus-ai (pytest; 110 collected: 90 pass + 20 vector skips in debug)

Fakes: `fake_nucleus.py` (the internal API), `fake_provider.py` (models),
`fake_mcp.py` (a real in-process MCP server with readOnlyHint labels).

| File | What it proves |
|---|---|
| test_acceptance.py | Layer acceptance end to end — a trigger in, the right events out |
| test_approvals.py | item 2: write tools pause (DeferredToolRequests), the pause POST to nucleus, resume with decisions, deny wording |
| test_ask_user.py | item 5: the ask_user external toolset — present only on interactive, question-capable runs; answers return as tool results |
| test_budget.py | item 15: prompt budget — stable sections first (cache rule), droppable priorities, protected plan never dropped |
| test_cost.py | usage records per call (chat_reply/router/memory), token counts, the batch POST shape |
| test_delegation.py | item 46: call_persona depth-1 delegation; the inner job's composite msg ids; no delegation tool inside |
| test_dependencies.py | the pins import and the version fences hold |
| test_discovery.py | tool catalog building from capability rows + stored MCP tool lists |
| test_embed_endpoints.py | embed/delete endpoints incl. the embedder spec riding each call |
| test_fallbacks.py | item W7: primary fails → fallbacks in order, with their own keys |
| test_history.py | history policy — non-completed rows dropped (status from nucleus), windowing |
| test_mcp_dial.py | Layer 1: dialing a live (fake) MCP server, auth header, read/write hints from readOnlyHint, unlabeled = write |
| test_model_check.py | the check endpoint's categorised failures (bad key / unknown model / timeout) |
| test_nudges_memory.py | nudges reach a running reply; the memory pass records recall entries |
| test_output_types.py | classifier/resolver/markers/recovery for the eight output types |
| test_retrieval.py | Layer 3 decision 10: retrieval refs event, context sources |
| test_router.py | item 13: the router screening run and deep escalation |
| test_search_and_mcp_tools.py (4) | Step 6A: POST /search/messages/ ranking across projects + key gate (skip without vector); POST /mcp/tools/ live dial with read hints + dead server 502 |
| test_tools.py | toolset_builder — capabilities, tool_levels auto/ask/off, approval_policy |
| test_turn_rules.py | Layer 6: step_context clipped block, approved_plan protected block, preflight acts-at-all rule |
| test_vector_db.py (the 20 skips) | txtai+pgvector store: upsert/search/delete, chunking, reembed — needs the vector postgres |

---

## 3. What is NOT covered by tests (known, on purpose)

- A REAL provider behind a persona (model quality, streaming against live
  APIs) — tests fake the provider.
- A REAL OAuth provider's registration/consent screens — faked; first live
  Connect click is the true test.
- The portal's own pieces (claim page, phone-home function, relay) — they
  have written contracts, no code yet.
- The frontend — FRONTEND-REVAMP.md is its spec.
- Production switch-over paths (ChromaDB removal, .pyc image) — Step 8's
  tests when it lands.
