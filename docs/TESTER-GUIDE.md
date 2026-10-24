# NeuralOps Nexus 1.0.0 — Tester's Guide

**Written 2026-10-23.** A feature-by-feature manual test of everything the
product does today, written for a tester who has never seen the system.
Work top to bottom — later sections use things built in earlier ones.
Record every case as **PASS / FAIL + one line on what you saw** (screenshot
on every FAIL). Report with the case id, e.g. `T-12 FAIL — refusal message
never appeared`.

**What you need before starting:**
- The web app URL and a NeuralOps server that is up (ask the owner).
- An account with **admin** rights on that server, and a second throwaway
  email you can receive invites on.
- At least one AI provider API key (any of OpenAI / Anthropic / DeepSeek /
  Google — ask the owner which to use). Treat it as a secret.
- A second browser (or a private window) for the two-user tests.

**General rules while testing:**
- AI replies cost real money. Prefer the cheapest model offered. Keep
  prompts short.
- When an **approval card** appears, read it before clicking — approving is
  part of the test.
- Anything odd that has no test case: note it anyway, with a screenshot.

---

## 1. Sign-in and the shell

**T-01 — Portal sign-in.** Open the web app → sign in with your account.
Expect: you land in the workspace; your name/avatar shows in the profile
button.

**T-02 — Local (offline) password.** Open your profile → set a local
password. Sign out → sign in using the local password path.
Expect: both sign-in roads work; the local one does not need the portal.

**T-03 — Version.** Open the about/version display.
Expect: app shows **1.0.0**; no "server too old" warning anywhere.

**T-04 — The pane rail.** Open any topic. The right-side rail must offer
exactly four panes: **Topics, Context, Schedules, Project** — each opens.
There is no Recall pane and no Deliverables pane (removed in 1.0.0).

## 2. Workspace: projects, channels, topics

**T-05 — Create.** Create a project → a channel in it → a topic in the
channel. Expect: each appears immediately in the tree; the topic opens
with an empty chat and the composer ready.

**T-06 — Plain chat + realtime.** Send a text message. In a second browser
signed in as the same user, open the same topic.
Expect: the message is there; a new message sent from one window appears
in the other within a second or two, no refresh.

**T-07 — Rename/archive.** Rename the topic; archive it; unarchive it.
Expect: the tree follows each change; an archived topic leaves the active
list but its history is intact when reopened.

## 3. Models (`/add-model`)

**T-08 — Register with Check.** Type `/add-model`. Fill: display name,
provider, the **bare model id** (e.g. `gpt-4o-mini` — no provider prefix),
the API key. Click **Check**.
Expect: Check calls the real provider and succeeds; Save is then allowed;
the model card appears. Defaults (context window, output cap) prefill
when you blur the id field.

**T-09 — Check catches a bad key.** Register again with a wrong key.
Expect: Check fails with a readable error; the model is not usable.

**T-10 — Attach to project.** Attach the good model to your project.
Expect: only attached models are offered when building personas there.

## 4. Personas (`/add-persona`)

**T-11 — Create a basic persona.** `/add-persona`: name, the model, a
short system prompt. Save.
Expect: the persona card appears; the dialog offers seats in this order:
Model → Router → Deep → Fallbacks → Advisor. There is **no Recall
checkbox** anywhere in the dialog (removed in 1.0.0).

**T-12 — First reply.** In a topic: `@YourPersona say hello in one line.`
Expect: a reply arrives; the topic's running cost line updates and is
labeled as estimated.

**T-13 — Stop and nudge.** Ask for something long ("write 10 paragraphs
about rivers"). While it runs, press **Stop**. Ask again, and this time
send a **nudge** ("make it about mountains instead") while it runs.
Expect: Stop ends the reply where it is; the nudge visibly steers the
rest of the reply.

**T-14 — @session.** Send `@YourPersona @session let's talk`. Then send a
follow-up **without** mentioning it. Then `@session close`, and one more
message. Expect: mid-session messages get replies without re-mentioning;
after close, a plain message gets no AI reply.

## 5. Output directives

In one topic, one at a time, each with a tiny prompt:

**T-15 — `@chart`** ("plot 3,1,4,1,5 as a line") → a rendered chart.
**T-16 — `@table`** ("3 planets with diameters") → a real table.
**T-17 — `@diagram`** ("a 3-step login flow") → a rendered diagram.
**T-18 — `@form`** ("a 2-field feedback form") → a usable form.
**T-19 — HTML page** ("a tiny page with a heading") → a sandboxed preview.
**T-20 — Terminal honesty (IMPORTANT).** Ask a persona **without** shell
capability (or with `date` not allowed): "run the date command".
Expect: it does NOT print an invented transcript. Either a real tool run
happens (visible tool row + today's real date) or the reply says
`# not executed: <reason>`. Fabricated output = automatic FAIL, report
immediately.

## 6. Tools, approvals, questions

**T-21 — Tool approval card.** Give the persona shell capability with
per-tool level **ask**. Ask it to list files in the project folder.
Expect: an approval card appears; **Deny** first → the persona copes
without the tool; ask again and **Approve** → a real tool row and real
output.

**T-22 — Persona asks you.** Give it a task missing one detail ("book the
meeting at the usual time" when no usual time exists).
Expect: if it needs the answer, a question/choice card appears; answering
resumes the run.

**T-23 — Plan-first (preflight).** Edit the persona: require a plan first.
Give it a multi-step task. Expect: it posts a plan and waits; approving
the plan starts the work.

**T-24 — Spend limit.** On the project overview pane set a monthly spend
limit of $0.01. Ask the persona anything.
Expect: your message posts, the AI reply is **refused** with a message
naming the ≈spend and the cap. Remove the limit → replies work again.

## 7. Routing (router / deep bench / fallbacks)

Needs 2–3 models attached. Edit the persona: a cheap model in the Router
seat, the standard model, and (if available) one deep-bench model.

**T-25 — Trivia stays cheap.** Ask "what's 2+2?".
Expect: the router answers inline — no hand-off shown.

**T-26 — Ordinary work hands to standard.** Ask for a short real task.
Expect: the reply shows "Handed to <standard model>".

**T-27 — Hard work escalates.** Ask something genuinely hard (a tricky
coding task). Expect: "Handed to" a deep-bench model.

**T-28 — Fallback.** (With the owner) break the standard model's key, ask
again. Expect: the reply arrives from a fallback and is labeled
"(fallback)"; nothing crashes. Restore the key.

## 8. MCP servers (`/add-mcp`) and the gateway

**T-29 — Catalog tile + token auth.** `/add-mcp`, pick a catalog entry
(e.g. GitHub) or a test server the owner names; authenticate with a token.
Expect: on save the server's **tool list** is fetched and shown with
read/write labels; Refresh re-fetches it.

**T-30 — Persona uses the MCP tool.** Attach the server to the persona,
set its tools to **ask**, then ask for something that needs it.
Expect: approval card → real result from the real service.

**T-31 — Gateway.** Mint a personal gateway token in the UI. Point an MCP
client (Claude Desktop/Cursor — or the owner runs it) at
`https://<server>/api/v1/mcp/` with `Authorization: Bearer nxg_…`.
Expect: the client can list projects/topics and post a message — and sees
ONLY what your account may see. A revoked token stops working.

## 9. Routines, schedules, chains

**T-32 — Routine.** In a topic run `/incident-summary` (or any listed
routine) with a short scenario. Expect: the reply follows the routine's
method, visibly different from a plain ask.

**T-33 — Schedule.** Create a schedule that fires a persona query a few
minutes from now in this topic. Expect: it fires on time, unattended (it
never stops to ask questions); the Schedules pane shows it and its last
run.

**T-34 — Chain: build and run.** Build a chain (currently labeled
"Runbook") with 2 persona steps (step 2's prompt builds on step 1) and a
**supervisor** persona that is NOT one of the step personas; redos = 1.
Run it with ▶ → "This chat".
Expect: the steps post one after another in the topic with a progress
banner; each stage gets a supervisor verdict.

**T-35 — Supervisor is fair.** In T-34's run, a stage that does its job
but is worded differently than the supervisor would word it must get
**APPROVE** — a REDO purely about style/tone = FAIL. Then edit a step to
demand strict JSON only, run with a weak model: a real format violation
gets **REDO with a note naming the concrete problem**.

**T-36 — Checkpoint.** Add a checkpoint step ("Happy with the draft?").
Run. Expect: the run parks and asks in the chat; your answer rides into
the next step; the run history shows "answered".

**T-37 — Stop + history.** Start a run and Stop it mid-way. Open the
chain's run history. Expect: every run listed newest-first with per-step
outcomes (done/failed/skipped/stopped, attempts, verdicts, durations) and
an "Open chat" that lands in the right topic.

## 10. Team, invites, rights

**T-38 — Topic-only invite.** `/invite <second-email>` in ONE topic. Sign
in as that user (second browser). Expect: they see that topic and NOTHING
else — no other topics, channels, projects.

**T-39 — Viewer can post, not call (1.0.0 change).** As that invited
viewer: the composer is visible (no read-only banner); a plain message
posts and everyone sees it; @mentioning a persona is **refused with a
worded error**; plain messages still work after the refusal.

**T-40 — Rights walls.** As the viewer, try to reach admin surfaces
(models, personas, MCP screens, project settings). Expect: read-only or
hidden everywhere; nothing editable leaks.

**T-41 — Project invite + persona invite.** `/invite <email> project`
grants the whole project; `/invite @Persona` adds a persona to the topic.
Expect: both behave as described.

## 11. Memory (1.0.0 hardening — test carefully)

**T-42 — Transcripts are never replayed as fresh.** In topic A, have a
persona run a real shell command (approve it). Let the reply finish. Open
a NEW topic B, same persona: "what command did we run earlier and what
did it show?" Expect: a SUMMARY that says it is remembered ("from our
earlier work…"), with NO `$`-style transcript and NO pretense of a fresh
run (no tool row = it must not claim it just ran). A verbatim replayed
transcript = automatic FAIL, report immediately.

**T-43 — Facts survive.** In topic B ask for the actual fact ("what files
were in the folder?"). Expect: the useful fact is remembered — only the
raw transcript form is banned.

## 12. Project files

**T-44 — Files pane.** Have a persona write a small file ("save a file
notes.md with three lines"). Open the Project pane.
Expect: the file is listed; it downloads; markdown/code/images render in
the viewer; the raw view is sandboxed and size-capped.

## 13. Usage and costs

**T-45 — Usage page.** After the tests above, open Usage.
Expect: totals are internally consistent (topics sum to project, project
to company); a "From cache" stat and a "By kind of work" table exist
(Chat replies / Router screening / Memory passes / Embeddings); every
money figure is labeled estimated.

## 14. Inbound hook

**T-46 — Hook fires a persona.** Create an inbound hook for a topic (ask
the owner for curl access). POST a short payload to the hook URL.
Expect: the persona answers in that topic as if asked; a bad token is
rejected.

---

## Known at 1.0.0 (do not file as bugs)

- Chains are labeled **"Runbook"** in the UI; the rename to "Chain" ships
  in 1.1.0. There is no `@ChainName` invocation yet — chains run from the
  ▶ button or a schedule.
- No connector tiles with icons yet; MCPs are added via `/add-mcp` or the
  catalog list (tiles ship in 1.2.0).
- Personas cannot register models or set up the system (the setup copilot
  ships later); `/add-model` and the dialogs are the only path.
- Free-model preset tiles are not in yet (1.2.0).

## Reporting

One line per case: `T-07 PASS` / `T-24 FAIL — reply was not refused, it
answered and billed $0.002`. Screenshots on every FAIL. Send the full list
in one message, cases in order. Anything outside the list that looks wrong:
report it with steps to reproduce.
