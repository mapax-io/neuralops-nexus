# NeuralOps Nexus

A self-hosted team workspace where every conversation can pull in an AI
persona — a plain LLM, or one with real tools (MCP servers) — right in the
chat. Projects → Channels → Topics, human members and AI personas side by
side: `@mention` a persona, shape its reply with an output directive
(`@chart`, `@table`, `@diagram`, `@form`, …), put work on a schedule, or run
a whole multi-step **chain** with a supervisor persona reviewing every stage.

Everything is private. You run it on your own server, on your own data, with
your own model provider keys. The only things that ever leave your server:
login to our identity service (and even that has an offline fallback), and a
single anonymous usage total (phone-home). Nothing else, ever.

## Architecture at a glance

| Service | What it does | Stack |
|---|---|---|
| `nucleus` | The orchestrator — auth, rights, workspace, chat, scheduling, chains, the REST API and the MCP gateway | Django + Django Ninja |
| `nexus-ai` | The AI engine — runs the model, builds prompts and toolsets, calls MCP tools, embeddings and semantic search | FastAPI + pydantic-ai |
| `centrifugo` | Real-time transport — message delivery to the browser | Centrifugo |
| `nginx` | Reverse proxy — the single entry point | nginx |
| `postgres` | Relational data AND the vector store (pgvector) — one database for both | PostgreSQL + pgvector |
| `redis` | Celery broker + Centrifugo engine | Redis |

One shared application image (`neuralops`) runs nucleus, nexus-ai and
centrifugo as separate services, each with a different `command:`. There is
no frontend service to run — the web UI is hosted; you connect it to your
own server.

> The AI engine was rebuilt from scratch (`modules/nexus-ai`) and the whole
> backend revamped around it — Steps 0–8, all owner-verified; see
> [`docs/NUCLEUS-REVAMP.md`](./docs/NUCLEUS-REVAMP.md). The revamp shipped
> as **1.0.0** — see [`docs/RELEASE-NOTES-1.0.0.md`](./docs/RELEASE-NOTES-1.0.0.md).

---

## 1. Self-hosting NeuralOps

Pre-built Docker images, no source code, no local builds. You connect the
official NeuralOps web app to your server afterward.

### Quick install (recommended)

On a Linux server (Ubuntu 22.04/24.04, Debian 12, x86_64 or arm64, 4GB+ RAM):

```bash
curl -fsSL https://get.neuralopsnexus.ai | bash
```

The installer checks your machine, installs Docker if missing, generates your secrets once, and asks how you want to reach the server:
- **Tailscale (recommended for home/office machines):** permanent HTTPS address via Tailscale Funnel; teammates install nothing.
- **A domain name (for cloud servers):** automatic HTTPS certificate via Caddy.

Careful users can download, inspect, and run:
```bash
curl -fsSL https://get.neuralopsnexus.ai -o install.sh
less install.sh
bash install.sh
```

---

### Manual install (advanced)

| | |
|---|---|
| **What you need** | Docker with Compose v2; ~4GB RAM; one reachable port (a domain + reverse proxy, [Tailscale Funnel](https://tailscale.com/kb/1223/funnel), or a load balancer); a NeuralOps account. |
| **What you run** | Fetch `docker-compose.neuralops.yaml` and the two env templates → `docker run --rm noamanfaisal/neuralops:latest init-secrets > neuralops/secrets.env` (generates your deployment's secrets, SECRET_KEY included) → fill in your server URL → `mkdir -p ./projects && sudo chown -R 1000:1000 ./projects` (the folder personas' file tools write into) → `docker compose up -d`. |
| **First run** | Create the vector database once, then `migrate`, `seed_permissions` and `seed_catalog` (exact commands below) — then **claim the server from the app**: it shows a short code, you sign in at the portal and type the code there, and you become the owner. No other shell step. (`manage.py create_owner` remains as the air-gapped fallback.) |
| **Time** | 10–15 minutes. |

Your secrets (`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `INTERNAL_API_KEY`,
`POSTGRES_PASSWORD`, the two Centrifugo keys) are generated fresh per
install — nothing shared with anyone else's deployment, nothing baked into
the public image. **Never re-run init-secrets on an existing install** — it
would replace your live database password.

First-run commands, against the running stack:

```bash
# once — the engine's vector store: its own database on the same postgres
docker exec neuralops-postgres sh -c 'psql -U "$POSTGRES_USER" -c "CREATE DATABASE nexus_vectors"'
docker exec neuralops-postgres sh -c 'psql -U "$POSTGRES_USER" -d nexus_vectors -c "CREATE EXTENSION vector"'

# the schema, the rights registry + default roles, the model/MCP catalog
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus \
  /opt/venv/nucleus-env/bin/python manage.py migrate
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus \
  /opt/venv/nucleus-env/bin/python manage.py seed_permissions
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus \
  /opt/venv/nucleus-env/bin/python manage.py seed_catalog
```

**Upgrading an existing install — gotchas** (each one found on a real
install):

- Keep `NEURALOPS_IMAGE` in `neuralops/infra.env` in sync at every version
  bump — an old pinned tag quietly runs the old release.
- Your postgres **volume** carries the password it was created with. Never
  wipe it with `docker compose down -v`; if you ever intend a truly fresh
  database, remove only that one volume by name.
- A `secrets.env` generated before SECRET_KEY joined init-secrets makes the
  server refuse to boot (by design). **Append** one line — never re-run
  init-secrets on an existing install:
  `docker run --rm noamanfaisal/neuralops:latest init-secrets | grep ^SECRET_KEY >> neuralops/secrets.env`
- Upgrading from a pre-1.0 install (postgres:17-alpine): the postgres image
  is now `pgvector/pgvector` (same PG major). One-time follow-ups:
  `REINDEX DATABASE` (collation change), then create `nexus_vectors` + the
  `vector` extension as in the first-run block above.

**Offline logins:** sign-in goes through the NeuralOps portal by default,
but every member can set a local password in their profile — then the server
signs them in entirely on its own, no internet needed.

---

## 2. Using NeuralOps

Type `/` in the message box to see every command, `@` to mention a persona
or attach context.

### Add your first AI model
**`/add-model`**: a display name, the **provider** (openai, anthropic,
google, deepseek, ollama, or any OpenAI-compatible endpoint), the **bare
model id** (e.g. `gpt-4o`, `claude-haiku-4-5-20251001` — no provider prefix),
an optional API base, and the key (stored encrypted). A **Check** button
verifies the model with the provider before you save. A model becomes
visible to a project when an admin *attaches* it there.

### Add an MCP server (tools)
**`/add-mcp`** or pick from the built-in catalog (GitHub, Jira/Confluence,
Postgres, Slack, Google Drive, …). HTTP/SSE servers get their **tool list**
fetched and stored on save (with read/write labels), plus a Refresh button.
Three ways to authenticate:
- **Nothing to fill in:** modern MCP servers support OAuth dynamic
  registration — click **Connect** and your server registers itself.
- **Static secrets:** paste a token (e.g. a GitHub PAT).
- **Your own OAuth app:** paste its client id/secret — the universal,
  air-gapped fallback.

### Add a persona
**`/add-persona`**: the name you'll `@mention`, exactly one model, an
optional advisor model and fallbacks, zero or more MCP servers (a persona
with no servers is a plain LLM — there is no separate "agent" object), its
system prompt, and per-tool levels (auto / ask / off). A persona can also be
gated to *propose a plan first* and act only after a person approves.

### Talk, steer, approve
```
@Layla show me the sales trend @chart
```
Mention several personas at once; add `@session` to keep talking without
re-mentioning (`@session close` ends it). While a reply runs you can **stop**
it or **nudge** it with extra instructions. When a persona needs permission
for a tool, or asks you a question, a card appears — your decision resumes
the run (undecided cards expire after 24h). Every reply's cost lands in the
topic's running total — always labeled *estimated*.

### Routines, schedules, chains, hooks
- **Routine** — a saved team method invoked with `/name` for one reply
  (four built-ins in every project).
- **Schedule** — a persona query (or a simple chain) fired on a clock,
  unattended: scheduled runs never stop to ask questions.
- **Chain** — a saved multi-step run: persona steps that build on each
  other, optional **checkpoint** steps that wait for a person's answer, and
  an optional **supervisor** persona that reviews every stage (approve /
  redo with notes / fail) right in the chat.
- **Inbound hook** — a URL outside systems can POST to, making a persona
  answer in a topic.

### Use your server AS a tool (MCP gateway)
Mint a personal gateway token in the UI (owner/admin tier), point Claude
Desktop, Cursor or any MCP client at `https://<your-server>/api/v1/mcp/`
with `Authorization: Bearer nxg_…` — and it can list your projects, post
messages, ask your personas, search your team's memory and run your chains,
always with exactly *your* permissions.

### Project files
Every project has a folder on the server that personas' filesystem tools
write into. Browse it, download any file, or view it rendered
(markdown/code/images) straight from the project — sandboxed, size-capped.

### Invite people
`/invite someone@example.com` (this topic) · `/invite someone@example.com
project` (whole project) · `/invite @Persona` (add the persona here). A
person invited to one topic sees that topic and nothing else.

---

## 3. Running from source (development)

One compose file, two profiles. The `dev` profile builds the unified image
locally and bind-mounts `modules/nexus-nucleus` and `modules/nexus-ai` over
the baked-in copies with `--reload` — edits apply live, and it is the SAME
image and code paths self-hosters run, so bugs reproduce faithfully.

```bash
git clone git@github.com:mapax-io/neuralops-nexus-backend.git
cd neuralops-nexus-backend
git checkout dev

cp neuralops/infra.env.example neuralops/infra.env     # set COMPOSE_PROFILES=dev
cp neuralops/app.env.example neuralops/app.env
docker build -f neuralops/Dockerfile -t neuralops:dev-local .
docker run --rm neuralops:dev-local init-secrets > neuralops/secrets.env

docker compose -f docker-compose.neuralops.yaml \
  --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
  up -d
```

Dev ports differ from production on purpose so both can coexist: nginx
**8096**, nexus-ai **8021**, Postgres **5496**, Redis **6396**; data lives in
separate `neuralops_*_dev` volumes.

First run, against a fresh database:

```bash
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev \
  /opt/venv/nucleus-env/bin/python manage.py migrate
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev \
  /opt/venv/nucleus-env/bin/python manage.py seed_permissions
# then claim the server from the app (the code flow), or air-gapped:
docker exec -it -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev \
  /opt/venv/nucleus-env/bin/python manage.py create_owner
```

- `migrate` creates the schema.
- `seed_permissions` seeds the rights registry and the four default roles.
  Skip it and permission checks fail with `Unknown right code`.
- The claim: the app's setup screen shows a short code; sign in at the
  portal and type it there — first verified claim becomes the owner.
- `seed_avatars` (optional) fetches an avatar pool.

Run the test suites the same way:

```bash
docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus-dev \
  /opt/venv/nucleus-env/bin/python manage.py test -v 1 --noinput
docker exec -w /nexus/ai neuralops-nexus-ai-new python -m pytest -q
```

To reach a dev server from the hosted frontend without opening router ports,
use Tailscale Funnel on the nginx port and set the resulting URL as
`NEURALOPS_SERVER_URL`.

> The older `docker-compose.yaml` dev split (separate per-service images,
> local react-app) has been retired from this repo.

---

## 4. Documentation map

Six living documents in [`docs/`](./docs) — each versioned with its own
changelog. Everything older lives in `docs/_archive/` (history, not
instructions).

| Doc | What's in it |
|---|---|
| [`docs/CHANGE-PROMPT.md`](./docs/CHANGE-PROMPT.md) | **Start here to work on the code** — the whole system brief: architecture principles, module maps, diagrams, requirements, lessons, how changes are made and verified |
| [`docs/NUCLEUS-REVAMP.md`](./docs/NUCLEUS-REVAMP.md) | The master record of the revamp — every design ruling, what was built where, every owner-verified step (0–8) |
| [`docs/API.md`](./docs/API.md) | Every endpoint — public, user, MCP gateway, internal, engine — with auth styles and rights; live OpenAPI at `/api/v1/openapi.json` for Postman |
| [`docs/CONCEPTS-AND-ROLES.md`](./docs/CONCEPTS-AND-ROLES.md) | Every core object explained, plus the full rights/roles system (all 47 rights, the four roles, the topic-only invite case) |
| [`docs/TESTS.md`](./docs/TESTS.md) | The test catalog — every suite and what it guarantees (464 backend + 118 engine tests) |
| [`docs/FRONTEND-REVAMP.md`](./docs/FRONTEND-REVAMP.md) | The web UI's contract — every event, screen and error wording the frontend builds against |

### Contributing

Fork [mapax-io/neuralops-nexus-backend](https://github.com/mapax-io/neuralops-nexus-backend)
(uncheck "Copy only the main branch"), branch off `dev` as `feature/<name>`,
open a PR against **`dev`** with a full description. Read
`docs/CHANGE-PROMPT.md` first — it is the contract for how changes are made
(design discussed and recorded, acceptance tests with every change, nothing
merged unverified). See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and
[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

> **Branch notice:** `dev` is the active development branch — clone and
> build from it. `master`/`main` may lag behind.

---

## 5. License

NeuralOps Nexus is licensed under the **NeuralOps Nexus Source Available
License 1.0** — source-available, not an OSI-approved open source license.
See [`LICENSE`](./LICENSE) for the full text.

In short: you're free to use, modify, self-host, and distribute this
software, but you may not offer it to third parties as a competing hosted or
managed service, and you may not circumvent any license-gated functionality
or strip the software's notices. See the LICENSE file's "Limitations"
section for the specifics.
