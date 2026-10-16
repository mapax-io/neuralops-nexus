# NeuralOps Nexus — set up from zero and verify everything yourself

**Document version: 0.1 (2026-10-15).** Written at the owner's request after
Step 8a: "I will configure the project from start, run all test cases, verify
all features, see the architecture being used." This is that walkthrough. You
drive; every command says WHY it exists. Nothing here assumes you remember any
chat session.

| Version | Date | What changed |
|---|---|---|
| 0.1 | 2026-10-15 | First version, written right after Step 8a (dev switch-over verified) |

**Honest scope note:** the backend is rebuilt and verified; the NEW frontend
is not built yet, and the portal pieces (claim page, OAuth relay) are specced
but not created. So Part 4 verifies features the way they exist TODAY — via
tests and the API — and says plainly which checks become browser clicks once
the frontend lands. This document gets updated as those arrive.

---

## Part 1 — The architecture on one page

**What the product is:** a chat workspace a company runs on its own server.
People and AI "personas" talk inside projects → channels → topics. Personas
are real identities backed by a model (OpenAI/Anthropic/Google), with tools,
memory, schedules, and chains.

**The six services** (all in `docker-compose.neuralops.yaml`, dev profile):

| Service (dev container) | Job | Why it is separate |
|---|---|---|
| `neuralops-nucleus-dev` | Django backend — the brain: auth, rights, workspace, chat orchestration, usage | It owns ALL business rules; nothing else decides who may do what |
| `neuralops-nexus-ai-new` | The engine (FastAPI + pydantic-ai) — the thinker: builds the prompt, runs the model, streams the reply | Model work is slow and library-heavy (torch, embeddings); it scales and ships separately. Nucleus orchestrates; the engine thinks |
| `neuralops-postgres-dev` | ONE postgres, TWO databases: `neuralops` (app data) and `nexus_vectors` (embeddings, via pgvector) | One thing to back up. ChromaDB is gone since Step 8a |
| `neuralops-redis-dev` | Queue for Celery (background jobs: schedules, chains, reindex) | Background work must survive a web-worker restart |
| `neuralops-centrifugo-dev` | Realtime pipe to the browser (our build is called nexus-transport) | The browser gets streaming tokens/events without polling |
| `neuralops-nginx-dev` | The front door: routes /api to nucleus, serves media, blocks `/internal/` from outside | One port to expose; the private roads stay private |

(Plus celery worker + celery beat — same nucleus image, different `command:`.)

**One reply's journey (the single most important flow):**

1. You type `@Sara check this` in a topic → browser calls nucleus
   (`chat/api.py`). Nucleus checks RIGHTS first (may you mention a persona
   here?) — every door does this, always.
2. Nucleus pre-creates the reply message row, then calls the engine:
   `POST /trigger/` with a TriggerJob (topic id, persona id, message id).
   This is the ONE trigger road — mentions, schedules, chain steps, gateway
   asks, all of them, same road.
3. The engine phones BACK to nucleus's internal API (locked with
   `X-Internal-API-Key`, and nginx 403s it from outside) to pull the persona,
   history, and tools. Nucleus never pushes prompts; the engine pulls what it
   needs.
4. The engine runs the model and streams 13 kinds of events back (deltas,
   tool use, questions, done). Nucleus's relay (`chat/relay.py`) turns them
   into message updates and pushes them to your browser through Centrifugo.
5. When done, the engine reports token usage; nucleus stores it as a
   UsageRecord (money is always ESTIMATED and labeled so; no foreign keys on
   usage rows, so deleting a persona never deletes the bill).

**The rights system in one paragraph (details: `CONCEPTS-AND-ROLES.md`):**
49 named rights (like `persona.mention`, `project.update`) live in a
registry. Roles (Owner/Admin/Member/Viewer by default) are bundles of rights,
assigned at company, project, or topic scope — a right granted high reaches
downward. EVERYTHING resolves to a real person: a gateway token acts AS its
person, a schedule fires AS its creator, a chain step runs AS its starter. If
a rights check cannot be answered, the answer is NO (fail closed), and a
thing you cannot see answers like a thing that does not exist.

**Diagrams:** the flow diagram and the full class diagram live in
`CHANGE-PROMPT.md` §2c. The full API list is `API.md`.

---

## Part 2 — Fresh setup from a clean clone

You can do this on node3 next to the existing checkout or on any Linux box
with docker. Steps 2.2–2.4 happen ONCE per deployment, ever.

**2.1 Clone and look around**

```bash
git clone <your fork url> neuralops && cd neuralops
ls docs/        # the seven live documents
ls modules/     # nexus-nucleus (backend), nexus-ai (engine), neuralops-react-app (UI)
ls neuralops/   # the install kit: Dockerfile, entrypoint, env examples
```

**2.2 Make the two env files**

```bash
cp neuralops/infra.env.example neuralops/infra.env
cp neuralops/app.env.example   neuralops/app.env
```

Why two: `infra.env` holds plain identifiers (database name/user, profile
choice) — not secret, safe to read over someone's shoulder. `app.env` holds
your server's own URL (`NEURALOPS_SERVER_URL`, and the matching
`CENTRIFUGO_ALLOWED_ORIGINS` — keep those two values identical). Open both
and fill the few marked values.

**2.3 Generate the secrets — ONCE, and never again**

```bash
docker run --rm noamanfaisal/neuralops:latest init-secrets > neuralops/secrets.env
```

Why: this writes five per-deployment secrets (database password, field
encryption key, internal API key, the two Centrifugo keys). **NEVER re-run
this on a live install** — it would mint a NEW database password that no
longer matches the database you already have, and new encryption keys that
cannot read your already-encrypted model keys. To add a new variable later,
APPEND a line to the file by hand.

**2.4 Create the projects folder with the right owner**

```bash
mkdir -p ./projects && sudo chown -R 1000:1000 ./projects
```

Why: project files live in a normal folder you can see and back up (owner's
ruling), not inside Docker's hidden storage. The engine runs as user 1000 and
cannot fix a root-owned folder by itself.

**2.5 Start the stack**

```bash
docker compose -f docker-compose.neuralops.yaml \
  --env-file neuralops/infra.env --env-file neuralops/app.env \
  --env-file neuralops/secrets.env --profile dev up -d --build
```

Why the three `--env-file` flags every single time: the compose file fills
`${POSTGRES_USER}`-style blanks from them at the moment you run the command.
Without the flags those blanks become empty strings and compose thinks every
container changed. (The five real secrets are ALSO loaded a second,
flag-proof way — `env_file:` inside the compose file — exactly because this
mistake was easy to make.)

**2.6 Create the vector database — once per postgres**

```bash
docker exec neuralops-postgres-dev sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE nexus_vectors;" && psql -U "$POSTGRES_USER" -d nexus_vectors -c "CREATE EXTENSION IF NOT EXISTS vector;"'
```

Why: app rows and vectors share one postgres but live in separate databases,
so a vector rebuild can never touch your chat data. The `vector` extension is
what makes postgres able to store and search embeddings (that is all
"pgvector" means). "already exists" on re-run is fine.

**2.7 Migrate and seed**

```bash
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py migrate
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py seed_permissions
```

Why: `migrate` builds the tables (through migration 0036 today);
`seed_permissions` writes the 49 rights and the four default role bundles —
without it every rights check fails CLOSED and even the owner can do nothing.

**2.8 What "healthy" looks like**

```bash
docker ps --format '{{.Names}}\t{{.Status}}'       # everything Up, nothing Restarting
docker logs --tail 5 neuralops-nucleus-dev          # a listening/ready line, no traceback
docker logs --tail 5 neuralops-nexus-ai-new         # "Application startup complete" (uvicorn)
```

A container that shows "Restarting" is crash-looping — `docker logs` it and
read the LAST traceback; that is always the real story.

---

## Part 3 — Run every test suite, and what each one proves

**3.1 Nucleus — 457 tests (~10 minutes)**

```bash
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py test -v 1 --noinput > test-output.txt 2>&1; tail -5 test-output.txt
```

Must end: `Ran 457 tests ... OK`. Why `--noinput`: a leftover test database
otherwise makes the runner stop at a yes/no prompt forever.

What the 457 prove, in plain words: the rights system (who may do what, and
that unknowns are refused), login (portal claim, offline/local login,
throttling), projects/channels/topics and invites, the whole chat road with a
FAKE engine (streaming, pauses, questions, stops), the file viewer's safety
wall, model config + the money math, the MCP gateway's eight tools and its
tokens, OAuth roads, schedules, hooks, and chains (supervisor, redo,
checkpoints). The scary tracebacks mid-log ("worker down", "the database went
away") are INJECTED failures — tests proving the app survives them.
Per-file detail: `TESTS.md`.

**3.2 Engine — 110 tests (~1 minute, after a one-time install)**

```bash
docker exec -w /nexus/ai neuralops-nexus-ai-new sh -c "pip install --user -q -r requirements-dev.txt && python -m pytest -q 2>&1 | tail -5"
```

Must end: `110 passed` — and **0 skipped**: since Step 8a the 20 vector tests
run against the real pgvector database (one of them rebuilds the whole index
with a new embedder and flips over without downtime). A "skipped" here is a
regression now. Why pytest is installed on the fly: test tools are not baked
into the shipped image on purpose. Note: the engine tests WIPE the `vx_*`
schemas in `nexus_vectors` each run — fine today (no real data); once you
have real embeddings, give tests their own database first.

**3.3 The baselines rule**

Any change ends at ≥ these numbers, all green: nucleus **457 OK**, engine
**110/0**, rights **49**, migrations **0036**. The method: a behavior is only
"done" when a test guarantees it and you saw that test pass yourself.

---

## Part 4 — Verify the features yourself

**4.1 Become the owner.** The portal claim page is not built yet, so today
you use the recorded air-gapped fallback:

```bash
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev /opt/venv/nucleus-env/bin/python manage.py create_owner --help
```

and follow its arguments (email, workspace name). Why this exists: a server
with no portal reachable must still be claimable by its owner. Once the
claim-code page exists, the real flow is: sign up on the portal → copy the
short code → paste it into the fresh install's setup screen.

**4.2 Log in without the portal.** Set a local password, then sign in — this
is the offline login road (24-hour tokens, 10 tries per 5 minutes):
endpoints `POST /api/v1/auth/local/set-password/` and
`POST /api/v1/auth/local/signin/`. Exact request bodies: `API.md` §1. The
bearer token it returns is what every other call below uses.

**4.3 Explore the API like the frontend will.** Import the live schema into
Postman: `GET /api/v1/openapi.json` (no auth needed). Why this is the honest
map: it is generated from the running code, so it cannot be stale.

**4.4 Add a real model and smoke-test the brain.** This is the first LIVE
model call (everything before used fakes):
1. Get one cheap API key (e.g. a mini/flash-class model).
2. `POST /api/v1/model-configs/` with provider, model name, and the key
   (stored encrypted; never returned by any API).
3. `POST /api/v1/model-configs/check/` — nucleus asks the ENGINE to actually
   call the provider. Expect `ok`. A wrong key answers with a plain reason
   (that road has six distinct refusal shapes, all tested).
4. Create a project (`POST /api/v1/projects/`) — watch it be born with a
   general channel, the fenced configure topic, a template chain, and its
   folder under `./projects/`.
5. Create a persona pointing at your model, then post a message mentioning
   it — and read the reply. That message just traveled the entire Part 1
   journey with nothing faked.

**4.5 The feature checklist.** Each line: what to do, and what "working"
means. Today these are API calls (Postman); each becomes a browser click once
the frontend screen exists.

| Feature | Try | Working means |
|---|---|---|
| Rights fail closed | Call a project you were not invited to | 404/403 — it does not exist for you |
| Invites | Invite a second user to ONE topic only | They see that topic and nothing else |
| File viewer | Upload to a project, browse, download | Paths outside the project folder are refused (the symlink wall) |
| Usage | After a few replies, `GET /usage/company/` | Token counts and an ESTIMATED cost, labeled |
| Embeddings | Configure the embedder, reindex a project | Search finds a message by meaning, not exact words; `vx_*` schemas appear in `nexus_vectors` |
| Schedules | Schedule a persona message | It fires unattended; the reply notes decisions instead of asking questions |
| Chains | Run the "Draft and review" template (add steps first) | Stages post visibly; the supervisor verdict appears in the topic; a checkpoint parks the run until a person answers; a checkpoint chain is REFUSED at scheduling with "run it by hand" |
| Gateway | Mint a token (`POST /gateway/tokens/`), call `POST /api/v1/mcp/` with it | The eight tools answer AS YOU — things you cannot see do not exist; revoke kills it at once |
| Hooks | Create an inbound hook, curl its URL | A message appears as the hook's creator; flooding hits 429 |
| Phone-home | Watch nucleus logs at startup | ONE line: install token, event, total tokens — nothing else leaves |

**4.6 The frontend.** `modules/neuralops-react-app` is the UI codebase; the
screen-by-screen work is specced in `FRONTEND-REVAMP.md` and briefed in
`FRONTEND-CHANGE-PROMPT.md`. As screens land, the checklist above moves from
Postman to clicks — this document gets a version bump each time.

---

## Part 5 — The online pieces (outside your server)

What they are, in order of building (contracts live in `NUCLEUS-REVAMP.md`):

1. **Claim-code page + two Supabase functions** — sign up on the portal, get
   a short code, paste it into a fresh install; the install is now YOURS.
   Until built: `create_owner` (4.1).
2. **Phone-home function** — receives the one-line report
   {install_token, event, total_tokens}. Deliberately knows nothing else.
3. **Vendor apps + OAuth relay** — you register a "NeuralOps" app at GitHub /
   Google / (third vendor) under YOUR account (only you can — it is your
   identity with the vendor); the relay is a small portal function holding
   those app secrets so they NEVER ship inside customer installs. Customers
   then click "Connect GitHub" and it works. Self-hosters who refuse the
   relay can paste their own client_id — both roads are built in nucleus
   already (Step 6C).

Status today: all specced, none created. The server-side halves are done and
tested; these are the portal-side halves.

---

## Part 6 — When something breaks (the habits that found every Step 8 bug)

1. **Read the LAST traceback** in `docker logs <container>` — the bottom one
   is the real error; everything above is consequences.
2. **"Permission denied" near a volume or bind mount** → ownership. The
   engine runs as user 1000; `sudo chown -R 1000:1000 <folder>` on the host,
   and for named volumes the image must pre-create the folder (ours do now).
3. **"No module named X" in the engine** → the lock file is stale. Never
   hand-edit it; regenerate (recipe in `CHANGE-PROMPT.md` lesson 14) and
   rebuild. If web search breaks, you lost the `duckduckgo` extra.
4. **Compose wants to recreate everything / POSTGRES vars "not set"** → you
   ran it without the three `--env-file` flags.
5. **Tests die on "database is being accessed by other users"** → a killed
   earlier run left a session; terminate and drop `test_neuralops`, rerun.
6. **A rights check refuses something you expected** → run
   `seed_permissions` (new rights must be seeded) — and remember refusal is
   the DESIGNED answer to any doubt.

The full hard-won list: `CHANGE-PROMPT.md` §7.
