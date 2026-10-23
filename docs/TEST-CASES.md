# NeuralOps — full acceptance test (from zero)

**Written 2026-10-21 for the owner's pre-release pass.** Start from a wiped
database, build everything from scratch, touch every feature once. Record
each case as PASS / FAIL + a note; put findings in one comments file keyed by
the TC id (see "How to report" at the bottom). Code state at writing:
backend 581d21b, frontend 79bcef4; suites nucleus 469 / engine 116 /
frontend 1140 all green.

**Updated 2026-10-21 (catalog-defaults + bundled-seed build, from your live
deepseek finding and the "setup pushes default data into db" ruling):**
migrations now end at **0041_catalog_windows**; suite targets are now
**nucleus 475 / engine 116 / frontend 1143**; TC-01, TC-01a and TC-09a below
reflect it. Fixed live mid-pass (hard-reload the frontend to pick them up):
(1) the id-suggestions dropdown offered Anthropic ids in OpenRouter's dotted
spelling (claude-sonnet-4.5), which Anthropic's API 404s — suggestions are
now re-hyphenated; (2) a deep-bench reply was labeled "· fallback" — the tag
now follows the server's "(fallback)" suffix only; (3) the router escalated
"what's 2+2?" — its instructions gained a keep-it bias; (4) RULED 20:37 and
BUILT: routing is now THREE-WAY — the router answers trivia itself, hands
ordinary work to the STANDARD model (lane 'standard', shows "Handed to
<standard>"), and reserves the deep bench for genuinely hard problems (lane
'deep'). Engine suite target is now **117** (new r10). For the routing
phase: trivia → router answers inline; an ordinary question → "Handed to"
the STANDARD model; a hard one → "Handed to" a bench model picked by its
strengths note.

**Updated 2026-10-22 21:49 (Stage 2 removal round, VERIFIED):** Recall (W5)
and Deliverables (W10) left the product entirely (owner's ruling; record in
FRONTEND-REVAMP §2k). Suite targets are now **nucleus 464 / engine 117
passed + 5 skipped / frontend 121 files, 1122 tests**; migrations end at
**nucleus 0042 + authn 0007**; the rights registry is **47**. Any TC that
mentioned the Recall pane or Keep-as-deliverable is void. Also in this
round: viewers can post plain messages (only persona calls are refused) and
the chain supervisor's verdict prompt has a pass-unless-broken bias.

---

## Progress — owner's pass, evening of 2026-10-21

Done and PASSED: TC-01 (wipe + migrate; 0041 pending confirm), TC-03 (claim,
after the EOF fix), models registered ×3 (gpt-4o-mini, deepseek-chat,
claude-sonnet-5-5 — note: Anthropic bare 4-5 ids don't exist on this account,
only dated ones; 5-5 ids are bare), TC-08/09 (check + generation fields),
project + persona built, max_steps=10. ROUTING (TC-24 area): the full
three-way ladder verified live — trivia inline by the router, ordinary/tool
work "Handed to DeepSeekChat", hard coding task "Handed to ClaudSonnet55"
with tools + an approval mid-run. Preflight plan approval PASSED
(@Faisal reviewed another persona's text after an approved plan).
SPEND LIMIT PASSED (cap $0.01 → worded refusal; 0/-5 refused; removed →
answers again). USAGE PASSED (page sums internally consistent; deepseek +
mini price math exact; provider dashboards match within rounding — Claude
$0.15 vs our $0.1562; register-time check-calls are unmetered by design).
Files + commands capabilities exercised by the date-ranges task.

UPDATE 2026-10-22 ~15:00 — **FABRICATED TOOL OUTPUT (worst finding of the
pass, FIXED):** asked to "run the date command", the persona printed an
invented transcript — wrong date (Oct 24 on Oct 22), an ls listing with files
that don't exist on disk (owner verified the real workspace), macOS-style
ownership on a Linux box, no tool rows. ROOT CAUSE: the terminal output
type's 0.8.0-era instruction literally said "show realistic output after
each command", and its classifier examples catch "run these commands" asks.
FIX (engine): terminal spec rewritten — output must be the run_command
tool's real return, refused/unavailable → "# not executed: <why>",
illustrative how-tos labeled "# example output — not executed"; PLUS a
general honesty rule appended to every tooled persona's tool-catalog prompt
section ("tool results are the only ground truth …"). +1 engine test (ot9)
→ **engine target is now 118**. RETEST: re-ask "run the date command" —
expect a real run (tool row + today's date) or an honest "not executed".
**VERIFIED live (owner, 15:01):** in a NEW topic the persona called
run_command (tool row, approved), the ls-only filter refused `date`, and the
reply printed `# not executed: command 'date' is not in the allowed list` —
the exact prescribed format, no invention. NOTE the replay lesson: in the OLD
topic the fake transcript kept coming back verbatim from history/memory —
fabrications that get stored are served again, so (a) the owner deletes the
poisoned recall entries, (b) the MEMORY-PASS HARDENING (never store tool
transcripts as facts) is REQUIRED BEFORE RELEASE, promoted from tuning.
ALSO: TC-12's "both lists refused" is UI-unreachable — the shell screen is a
mode selector (Any / Only these / All but these) with one list; the backend
guard stays API-only. Test the mode enforcement instead (allow only ls →
date refused at run time).

UPDATE 2026-10-22 14:35: TC-01a PASSED (`seed_catalog` → "Seeded 0 … 322 in
the file; existing rows left untouched" — the refresh had already written all
322, and the never-downgrade rule held, which is the point); TC-09a PASSED
(131072/8192 prefill); default-router-fills-empty-seat PASSED (owner: "thats
already done"). SUITES RUN 2026-10-22 16:28 (one log, suites-2026-10-22.log):
engine **118 passed, 5 skipped** ✓; frontend **125 files / 1143 tests + lint
clean** ✓; nucleus **475 ran, 2 errors** — both tests asserting the recalled
miswire (metadata["recalled"] == retrieval count); both rewritten to assert
the honest behavior (no recalled key; wire recalled=0). Re-run the two to
close nucleus:
`docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py test chat.tests.RelayTests.test_the_new_done_extras_land_on_the_row_and_the_wire chat.tests.RelayUsageTests.test_what_the_reply_retrieved_is_never_counted_as_remembered -v 1 --noinput`
Still due: that nucleus re-run, the two commits.

TC-38 ANSWERED (owner, 2026-10-22 20:51): **YES** — the embedder row is
visible in the UI; MISSING item 4's open question closes with nothing to
build. TEAM TEST PASSED (viewer reads all, edits nothing) with the one
composer finding below. GATEWAY PASSED (tools/list live, person-scoped).
MCP TC-13/14 PASSED. CHAINS PASSED (both modes). Stage 1 is COMPLETE once
the owner's sweep notes (if any) land.

FOUND 2026-10-22 20:06 (team test) — RULED: a Viewer saw "You have read-only
access to this chat" and could not post at all. Owner: "it should only
refrain user from calling persona" — viewers POST plain messages; only
persona mentions are refused (which the server already does, and its tests
pin). FIX (frontend, tonight's round): the composer's read-only gate keys on
the wrong right — allow composing for viewers, keep the mention refusal.
Also align any server-side right the UI was mirroring.

Still OPEN: fallback with a deliberately broken key (or defer); web_search with a FRESH
question (first attempt answered from project memory with no tool row —
verify the earlier message's trail had a real web_search row); web_fetch;
Web approval knob Ask/Off/Default; TC-12 shell allow+block guard; chains;
team/invites; recall-pane inspection ("Remembered N things" fires on trivia
— suspected memory-pass over-recording, owner to report what's stored);
gateway; UI sweep; TC-38 embedder row. SUITES to run: engine **117**,
frontend **1143**; then COMMIT both repos (seed file + .gitignore carve-out
ride the backend commit).

---

## Phase 0 — fresh start

- **TC-01 Wipe + restart.** Stop the stack and reset the DATABASE with your
  usual dev reset (drop the postgres volume/db). **Do NOT re-run
  init-secrets and do NOT touch neuralops/secrets.env** (append-only rule).
  Bring the stack up; run migrate; expect it to end at **0041_catalog_windows**
  with no errors. Restart nexus-ai-new and the frontend dev server; hard
  reload the browser.
- **TC-01a Seed the default catalog (new setup step, right after migrate).**
  FIRST TIME ONLY — generate the bundled file (downloads the latest catalog
  from GitHub; this is also the release-time step, commit the file after):
  `docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py seed_catalog --regenerate`
  Then, on this and every future setup — push the defaults into the DB
  (models, context windows, max outputs, rates; fills missing rows only):
  `docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py seed_catalog`
  Expect "Seeded N new catalog rows"; running it again says "Seeded 0" —
  that's the idempotence working, not a failure.
- **TC-02 Engine deps survive.** If the nexus-ai-new CONTAINER was recreated
  (not just restarted): re-run
  `docker exec neuralops-nexus-ai-new /opt/venv/nexus-ai-env/bin/pip install "pydantic-ai-slim[web-fetch]"`
  (MISSING 7c — needed until the next image build).

## Phase 1 — claim + sign-in

- **TC-03 Claim the install.** First visit → setup/claim flow → the owner
  account exists, workspace named. Sign out, sign back in (Supabase).
- **TC-04 Wrong password handling.** A bad sign-in explains itself; ~10 fast
  wrong local sign-ins hit a rate limit (Too Many Requests), not a crash.

## Phase 2 — workspace basics

- **TC-05 New project is born complete.** Create a project → it has a
  #general channel, a **configure** topic (gear visible to you), one example
  chain "Draft and review" (no steps, running it is refused with "add steps
  first"), and ONE "<Project> Capabilities" row on the MCP screen holding
  **all four** defaults: filesystem, shell, web_search, web_fetch (ruled
  2026-10-21: keep all four). That row is locked against deletion.
- **TC-06 Brief.** Project overview pane → write a brief (markdown) → saved
  note; preview renders; >8,000 chars is refused with the count.
- **TC-07 Channels/topics.** New channel; topics auto-name chat#N; rename a
  topic; archive a topic; unread dots appear for a closed topic.

## Phase 3 — models

- **TC-08 Register with check.** AI Models → register gpt-4o-mini with your
  (rotated!) key → the Check runs, shows latency, unlocks Register. A wrong
  key shows the categorised reason, never the raw provider text.
- **TC-09 Generation section.** Each register/edit dialog has Max reply
  tokens / Temperature / Strengths and weaknesses. Register your three
  models; set deepseek-chat's Max reply tokens to **8000**; write a distinct
  strengths line on each card (feeds TC-24). Card meta shows "reply 8k/16k".
- **TC-09a Catalog defaults prefill (added 2026-10-21 from your deepseek
  finding).** Needs TC-01a done (the seed put the sizes in the DB). Open
  Register, pick DeepSeek, type `deepseek-chat`, click out of the id field →
  Context window and Max reply tokens fill from the server's catalog
  (131072 / 8192 as of writing — the window matches the old table by
  coincidence; the 8192 max output is what the table never knew). Type your
  own number first → it is never overwritten by the lookup.
- **TC-10 Guards.** A provider-prefixed id ("openai/gpt-4o") is refused;
  terms must be accepted; deleting a model a persona uses is refused naming
  the persona; detaching one from a project a persona (any seat or bench)
  uses is refused too.
- **TC-11 Utility model.** Mark one config as the utility model; the badge
  shows; clearing it works.

## Phase 4 — MCP tool servers

- **TC-12 Built-in capabilities row.** Open the project's Capabilities row →
  the four capabilities editable; shell allow+block lists together are
  refused until one is kept.
- **TC-13 External server + tool list.** Add an external HTTP server (any
  reachable MCP, or your own) → its card shows "N tools · X read / Y write";
  **Refresh tools** re-fetches with a toast; the edit dialog's Tools section
  lists each tool with its read/write badge (unlabeled = write).
- **TC-14 Refresh failure is worded.** Edit the server's URL to a dead port →
  Refresh tools → the reason appears VERBATIM beside the button. Fix it back.

## Phase 5 — personas

- **TC-15 Create from catalogue + template.** Hire one from the persona
  catalogue (dialog pre-filled); create one from a prompt template; the
  {PERSONA_NAME} token fills with the typed name live.
- **TC-16 Composition.** The dialog order is Model → Router → Deep models →
  Fallbacks → Advisor; NO Temperature/Max tokens anywhere (hint points at
  the model card); Generation keeps Max steps + Proposes first + Recall.
- **TC-17 Deep bench.** Add TWO deep models → first row tagged "default
  pick"; arrows reorder; the primary model can never appear in the bench
  (picking it as Model drops it off the list). Card chips "deep bench · 2".
- **TC-18 Fallbacks + advisor.** Up to three fallbacks, ordered; advisor ≠
  model; inline "Register a new model" works from the model/router/advisor
  slots and lands in the right seat.
- **TC-19 Tools + approvals.** Tick the Capabilities row; a non-tool model
  disables/unticks servers with an explanation; Tool approvals set a level
  (auto/ask/off) and round-trip on edit.

## Phase 6 — chat core

- **TC-20 Mention + session.** @persona answers; "@persona @session" opens a
  session (pill message); plain messages then auto-trigger; "@session close"
  closes it, named.
- **TC-21 Output types.** "@chart plot 3,5,2 by day" → a rendered chart (a
  blank axis prefix or odd scale from the model must not break it — the
  fallback shows the data with a reason). @table too. Keep a chart as a
  deliverable; it appears in the Deliverables pane with versions.
- **TC-22 Steering.** Stop a streaming reply (caller only); nudge a running
  reply and see the persona take it; the context meter and spend ticker on
  the chat header update live and survive a reload.
- **TC-23 Approvals / questions / preflight.** A write tool pauses with an
  approval card (Allow runs it, Deny words it); ask_user shows the question
  card and your answer resumes; a "Proposes before acting" persona answers
  with a plan first, and approving it leads to the acting turn.

## Phase 7 — routing (the new brain)

- **TC-24 Router answers trivial.** Persona with Router=gpt-4o-mini: ask
  "what is 2+2?" → quick cheap answer, no hand-over; Usage shows a "Router
  screening" row.
- **TC-25 Bench pick by strengths.** Two deep models with different notes
  (one "best for code"). A hard CODE question → "Handed to <the code
  model>". A hard NON-code question → handed to the other (or the default
  first when unsure). The reply content comes from the deep model only.
- **TC-26 Typed turn skips the router.** "@chart …" on the routed persona →
  no router row for that reply (typed turns go straight to a capable model).
- **TC-27 No seats = plain persona.** A persona without router/deep behaves
  exactly as before.

## Phase 8 — project controls

- **TC-28 Default router.** Overview pane → Default router = gpt-4o-mini.
  A persona with an EMPTY router seat asks something trivial → screened
  cheap. A persona whose OWN router is set keeps its own. A persona whose
  standard model IS the default is not screened by itself.
- **TC-29 Spend limit.** Set the limit to $0.01 → any ask is refused naming
  "≈ $… of $0.01, estimated" (your message still posts). Remove limit →
  answers again. The pane shows "≈ $X spent this month".

## Phase 9 — usage

- **TC-30 Usage page.** "From cache" stat with a %, a Cached column, a "By
  kind of work" table (Chat replies / Router screening / Memory passes /
  Embeddings), totals with ≥ when rows are unpriced, every money figure
  labeled estimated. gpt-4o-mini should be priced by now (catalog refresh) —
  note if it still says no price.

## Phase 10 — team, chains, memory, gateway

- **TC-31 Invites + rights.** Invite a member scoped to one topic → they see
  only it; no configure gear; they cannot edit the brief, set the default
  router or spend limit (plain sentences instead); a viewer cannot mention
  personas (worded refusal).
- **TC-32 Chains.** Build a runbook: persona step + checkpoint question →
  Run now → the banner asks mid-run → answering continues it; the run
  history names you; scheduling that chain is refused ("run it by hand");
  a supervisor persona on a 2-step chain posts verdicts.
- **TC-33 Recall.** A persona records a decision ("we use Postgres") → the
  Recall pane lists it attributed; edit/remove under recall.manage; a
  persona with Recall off neither reads nor writes it.
- **TC-34 Search.** The message search finds an old message by meaning; with
  the worker stopped it still answers (literal fallback), no 500.
- **TC-35 Gateway.** Mint a token → raw value shown exactly once; the pasted
  client config reaches /api/v1/mcp/ (one tool call through it); revoke →
  the door shuts immediately.
- **TC-36 Schedules.** A daily schedule on a persona fires (or fire it by
  hand); one whose creator lost access is skipped with the worded reason.

## Phase 11 — shell / UI sweep

- **TC-37 Rail + panes.** Exactly six panes (Topics, Context, Schedules,
  Project, Recall, Deliverables) — no Terminal/Browser/Web; an
  activity-trail "Open" link opens a NEW BROWSER TAB; mobile pane picker
  lists the same set.
- **TC-38 Embedder row (open check, MISSING item 4).** Project settings:
  does an embedder row + "memory is being rebuilt" banner exist? Record
  YES/NO — if NO it becomes a small build, not a bug.

---

## How to report

One file, one line block per finding:

```
TC-25 FAIL
What I did: asked "write a sorting benchmark in python"
Expected: Handed to DeepSeek (its note says best for code)
Got: Handed to GPT-4o
Log/screenshot: <paste or filename>
```

PASSes need only `TC-xx PASS`. Anything outside the list is welcome as
`NEW: <what you saw>`. Hand me the file; I fix by TC id, and every fix ends
with the three regression gates re-run: **nucleus 469 · engine 116 ·
frontend 1140** (numbers grow only when a fix adds tests — I'll state the
new targets with each fix).
