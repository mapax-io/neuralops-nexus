# NeuralOps Nexus

A self-hosted team workspace where every conversation can pull in an AI persona — backed by a plain LLM or an agent with tool access (MCP servers) — right in the chat. Projects → Channels → Topics, human members and AI personas side by side, `@mention` to trigger a persona, `@directive` to shape its output (chart, table, diagram, form...).

Everything is private. You run it on your own server, on your own data, with your own model provider keys. Nothing leaves your server unless you configure it to.

## Architecture at a glance

| Service | What it does | Stack |
|---|---|---|
| `nucleus` | Orchestrator — auth, workspace, chat, REST API | Django + Django Ninja |
| `nexus-ai` | AI worker — runs the LLM/agent, embeddings, MCP tool calls | FastAPI + LiteLLM + pydantic-ai |
| `centrifugo` | Real-time transport — message delivery to the browser | Centrifugo |
| `nginx` | Reverse proxy — single entry point (`/api/`, `/admin/`, websocket) | nginx |
| `postgres` | Relational data | PostgreSQL 17 |
| `chromadb` | Vector store for embeddings / semantic context search | ChromaDB |
| `redis` | Celery broker + Centrifugo engine | Redis 7 |
| `mcps/` | Optional first-party MCP tool servers (SerpAPI, Odoo ERP, filesystem) | FastMCP |

There's no frontend service to run. The web UI is hosted — you connect it to your own server. (A local `react-app` container does exist, but only in the development profile — see [§3](#3-running-from-source-development).)

Curious how these fit together and why each tool was chosen? See [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 1. Self-hosting NeuralOps

The fast path: pre-built Docker images, no source code, no local builds. You connect the official NeuralOps web app to your server afterward — there's no separate frontend to install.

**→ Full step-by-step guide: [`SELF-HOST.md`](./SELF-HOST.md)**

The shape of it, so you know what you're signing up for:

| | |
|---|---|
| **What you need** | Docker with the Compose v2 plugin; ~4GB RAM; one port reachable from wherever you'll use NeuralOps (a domain + reverse proxy, [Tailscale Funnel](https://tailscale.com/kb/1223/funnel), or a cloud load balancer); an existing NeuralOps account. |
| **What you run** | Fetch `docker-compose.neuralops.yaml` and two env templates → generate your deployment's secrets → fill in your server URL → `docker compose up -d`. Nine containers, one shared image (`noamanfaisal/neuralops`) launched in different modes. |
| **Then** | `migrate`, `seed_permissions`, `create_owner` once against a fresh database; expose the port; connect the web app. |
| **Time** | 10–15 minutes. |

Your secrets (`FIELD_ENCRYPTION_KEY`, `INTERNAL_API_KEY`, the two Centrifugo keys) are generated fresh per install — nothing shared with anyone else's deployment, nothing baked into the public image.

> **A note on older instructions.** You may run into an earlier single-container flow using `noamanfaisal/neuralops-fat` and `bootstrap.py generate-env` / `init-db`, or an earlier multi-image "fat profile" using `install.sh`. Both are superseded by the guide above — see [`fat_docker.md`](./fat_docker.md) for the command cheat sheet and [`DECISIONS.md`](./DECISIONS.md) §20 for why the design changed. Don't mix them; pick the current one.

---

## 2. Using NeuralOps

Everything below is driven from inside the chat itself — type `/` in the message box to see all available commands, or `@` to mention a persona or attach context.

### Add your first AI model

Type **`/add-model`** in any chat. You'll need:

| Field | Notes |
|---|---|
| Name | Display name, e.g. "GPT-4o" |
| Model ID | LiteLLM format, e.g. `gpt-4o`, `anthropic/claude-haiku-4-5-20251001` |
| API Base URL | Optional — only for custom/self-hosted endpoints |
| API Key | Stored encrypted |
| Terms of service checkbox | Required before saving |

`/list-models` shows everything you've registered.

### Add an MCP server

*No MCP servers are configured on a fresh server by default.* Type **`/add-mcp`** and provide:

| Field | Notes |
|---|---|
| Name | e.g. "Odoo ERP" |
| URL | The server's `/mcp` endpoint |
| Transport | `streamable-http` (default), `sse`, or `stdio` |
| Server Type | Remote or Local |

The `mcps/` folder ships three ready-to-run example servers (SerpAPI shopping, Odoo ERP, filesystem) you can spin up with `cd mcps && docker compose up -d` and then register here. **Important:** when a persona actually calls a tool, the request comes from inside the `nexus-ai` container — register the MCP server's URL using your host's real IP, not `localhost`, or tool calls will fail with connection refused. `/list-mcps` shows everything registered.

### Add an agent

An agent pairs a model with an MCP server so a persona built on it can call tools. Type **`/add-agent`**:

| Field | Notes |
|---|---|
| Name | e.g. "ERP Agent" |
| AI Model | Required — pick from your registered models |
| MCP Server | Optional — pick one, or None for a plain-LLM agent |
| System Prompt | Optional instructions |

`/list-agents` to review.

### Add a persona

Personas are what you `@mention` in chat. Type **`/add-persona`**:

| Field | Notes |
|---|---|
| Name | Used as the `@mention`, e.g. "Layla" → `@Layla` |
| Backed by | **Agent** (model + tools) or **Model directly** (plain LLM, no tools) |
| System Prompt | Defaults to "You are {name}, a helpful AI assistant." |

`/list-personas` to review or manage existing ones.

### Invite a user

Type **`/invite`** followed by either an `@PersonaName` or an email address:

```
/invite @Layla                        → adds the persona to this project
/invite someone@example.com           → invites them to this topic
/invite someone@example.com project   → invites them to the whole project
```

Existing workspace users are added directly. A new address is pre-authorised, and emailed too when the server holds the identity project's service key.

### Create a project, channel, and topic

- **Project:** click **+** next to Projects in the sidebar → name + optional description.
- **Channel:** inside a project, **+** next to Channels → name + optional description.
- **Topic:** inside a channel, **+** next to Topics → title. This is the actual conversation thread.

### Talk to a persona

`@mention` any persona in a message to trigger it:

```
@Layla summarize the last quarter's numbers
```

You can mention multiple personas at once, and add an output directive to shape the reply — `@chart`, `@table`, `@diagram`, `@form`, `@code`, `@terminal`, `@html`, or `@text`:

```
@Layla show me the sales trend @chart
```

### `@session` — keep talking without re-mentioning

Add `@session` to open a running session with whichever personas you just mentioned — every plain message after that (no `@mention` needed) goes to them automatically, until the session times out (default 30 min, configurable per company) or you close it:

```
@Layla @session let's dig into this together
...then just type normally, no @mention needed...
@session close        (or "@session end")
```

### Schedule a persona

Personas can also run on a schedule instead of waiting for an `@mention` — a recurring query posted into a topic automatically (daily standup summary, hourly monitoring check). Schedules are per-topic; anyone who can chat in a topic can create one, and you can always pause or delete your own.

---

## 3. Running from source (development)

There are two development setups, in two different compose files. Pick by what you're working on:

| | **A — `docker-compose.neuralops.yaml`, `dev` profile** | **B — `docker-compose.yaml`, `dev` profile** |
|---|---|---|
| Use it for | Backend work (nucleus, nexus-ai) | Frontend work, or anything needing a local UI |
| Local frontend | ❌ none — connect the hosted app | ✅ `dev-react-app` on port 3003 |
| Image | Builds the unified `neuralops` image locally | Separate per-service dev images |
| Config | `neuralops/infra.env` + `app.env` + `secrets.env` | `.env` with `DEV_*` variables |
| Matches production | ✅ same image and entrypoint as §1 | ❌ older, separate build path |

Option A is the same image and code paths self-hosters run, so bugs reproduce faithfully. Option B is the older setup, still the only one with a local React app. Don't run both at once — they'd fight over the `neuralops-network` bridge.

### Option A — unified image, hot-reload backend

```bash
git clone git@github.com:mapax-io/neuralops-nexus-backend.git
cd neuralops-nexus-backend
git checkout dev

cp neuralops/infra.env.example neuralops/infra.env
cp neuralops/app.env.example neuralops/app.env
docker build -f neuralops/Dockerfile -t neuralops:dev-local .
docker run --rm neuralops:dev-local init-secrets > neuralops/secrets.env
```

Set `COMPOSE_PROFILES=dev` in `neuralops/infra.env`, then:

```bash
docker compose -f docker-compose.neuralops.yaml \
  --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
  up -d
```

Nine `*-dev` containers come up. `modules/nexus-nucleus` and `modules/nexus-ai` are bind-mounted over the baked-in copies, and both uvicorns run with `--reload`, so edits on the host apply live. Ports differ from production on purpose so the two can coexist: nginx **8096**, nexus-ai **8021**, Postgres **5496**, Redis **6396**. Data lives in separate `neuralops_*_dev` volumes.

Run the first-run commands the same way as production, substituting the dev service name:

```bash
docker compose -f docker-compose.neuralops.yaml --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
  exec nucleus-dev entrypoint.sh nucleus-env python manage.py migrate
```

...then `seed_permissions` and `create_owner` the same way. See [`SELF-HOST.md`](./SELF-HOST.md) step 5 for the full sequence and what each does.

### Option B — older dev profile, with local frontend

**Prerequisites:** Docker & Docker Compose, Git.

```bash
git clone git@github.com:mapax-io/neuralops-nexus-backend.git
cd neuralops-nexus-backend
git checkout dev

cp .env.example .env
```

`.env` is gitignored on purpose — `.env.example` is the tracked template every fresh clone starts from. `COMPOSE_PROFILES=dev` is already set in it, so a bare `docker compose up` picks the right profile with no extra flags. Edit `.env` and fill in the blank `DEV_*` values — each is documented inline, but at minimum:

| Variable | Purpose |
|---|---|
| `DEV_POSTGRES_USER` / `DEV_POSTGRES_PASSWORD` / `DEV_POSTGRES_DB` / `DEV_POSTGRES_URL` | Database credentials |
| `DEV_FIELD_ENCRYPTION_KEY` | Encrypts stored model API keys — generate with `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `DEV_INTERNAL_API_KEY` / `DEV_CENTRIFUGO_API_KEY` / `DEV_CENTRIFUGO_HMAC_SECRET` / `DEV_NEURALOPS_INSTALL_TOKEN` | Shared secrets — any random string, e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DEV_OPENAI_API_KEY` / `DEV_ANTHROPIC_API_KEY` | At least one, for your first AI model |
| `DEV_SUPABASE_SERVICE_KEY` | From your Supabase project settings → API (service_role key). `DEV_SUPABASE_URL`/`DEV_SUPABASE_ANON_KEY` are pre-filled — those are public by design |
| `DEV_NEURALOPS_SERVER_URL` | The URL *other people* will use to reach your server, e.g. `http://192.168.1.90:8081` — defaults to `http://localhost:8081`, which only works for you locally |

Verify nothing required is still blank, then bring the stack up:

```bash
docker compose config      # confirm no ${DEV_...} shows up empty
docker compose up -d
```

`docker compose ps` should show all 9 `dev-*` containers: `dev-nucleus`, `dev-celery`, `dev-redis`, `dev-nexus-ai`, `dev-transport`, `dev-nginx`, `dev-chroma`, `dev-postgres`, `dev-react-app`. Data persists in `./data/dev/`.

### First-run setup

Run these once, in order, against a fresh database:

```bash
docker compose exec nucleus-dev python manage.py migrate
docker compose exec nucleus-dev python manage.py seed_permissions
docker compose exec nucleus-dev python manage.py create_owner
docker compose exec nucleus-dev python manage.py seed_avatars     # optional
```

- `migrate` creates the schema.
- `seed_permissions` seeds the RBAC right codes (`project.list`, `project.create`, ...). Skip it and every permission check 500s with `Unknown right code`.
- `create_owner` is interactive. It needs a **NeuralOps account already created at the sign-up page** — if you don't have one it'll tell you to sign up first, then run again. It creates your workspace and grants you the Owner role.
- `seed_avatars` fetches a pool of DiceBear avatars so new users/personas get one automatically.

Order between `seed_permissions` and `create_owner` doesn't actually matter — both converge on the same Owner role row. `migrate` must go first.

Then open `http://<your-server-ip>:3003`. Both port 3003 (frontend) and `DEV_NGINX_HOST_PORT` (default `8081`, the API) need to be reachable from wherever your browser is.

### Exposing a dev server

To connect the *hosted* frontend to your local backend without opening router ports, use Tailscale Funnel:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale funnel --bg 8081
```

Set the resulting `https://<machine>.<tailnet>.ts.net` URL as `DEV_NEURALOPS_SERVER_URL` in `.env`, then restart both services that read it — `nucleus` builds it into API responses, and Centrifugo checks it for allowed WebSocket origins:

```bash
docker compose restart nucleus-dev realtime-dev
```

To stay fully local instead, set `DEV_NEURALOPS_SERVER_URL` to `http://localhost:8081` (or your LAN IP for other devices on your network), restart the same two services, and use the local `react-app-dev` at port 3003. To remap any host port, change the matching `DEV_*_HOST_PORT` variable rather than editing `docker-compose.yaml`.

---

## 4. Documentation map

### Deploying and running

| Doc | What's in it |
|---|---|
| [`SELF-HOST.md`](./SELF-HOST.md) | **The current self-host guide** — Compose + unified image, step by step |
| [`fat_docker.md`](./fat_docker.md) | Command cheat sheet for self-hosting, plus superseded older flows for reference |

### Understanding the system

| Doc | What's in it |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design and *why* each tool/framework was chosen over the alternatives |
| [`CONCEPTS-AND-ROLES.md`](./CONCEPTS-AND-ROLES.md) | Every core object (Company, Project, Channel, Topic, User, AI Model, Agent, MCP Server, Context, Knowledge Base) — philosophy + Django model — plus the full permissions/role hierarchy and its known gaps |
| [`DECISIONS.md`](./DECISIONS.md) | Product decisions, implementation rules, and constraints — **read before changing behavior** |
| [`STORY.md`](./STORY.md) | The narrative version — how the architecture evolved, what was tried and abandoned, and why |
| [`story/`](./story) | Deep-dive narratives on specific subsystems (auth architecture, permissions model, owner setup) |
| [`user-stories.md`](./user-stories.md) | Product requirements as user stories |
| [`CHAT_REVAMP_STRATEGY.md`](./CHAT_REVAMP_STRATEGY.md) | Design notes for the chat subsystem rework |
| [`mermaid.dbdesign`](./mermaid.dbdesign) | Database schema diagram (Mermaid source) |
| [`project-strategy/`](./project-strategy) | Product and go-to-market strategy notes |

### API reference

| Doc | What's in it |
|---|---|
| [`neuralops-backend-api-catalog-v2.md`](./neuralops-backend-api-catalog-v2.md) | Full REST + internal API reference with request/response fields, Django models, and the AI config layer |
| [`neuralops-backend-api-catalog.md`](./neuralops-backend-api-catalog.md) | Companion catalog — additionally covers the MCP tool servers, `nexus-ai`'s verify endpoints, and permission-scope prose |
| [`api-docs/`](./api-docs) | Generated API documentation |

Neither catalog is a superset of the other — each says at the top what the other uniquely covers.

### Contributing

| Doc | What's in it |
|---|---|
| [`how-to-contribute.md`](./how-to-contribute.md) | Fork/branch/PR workflow, commit conventions, code review process |
| [`TASKS.md`](./TASKS.md) | Full development task history + known gotchas |

Short version: fork [mapax-io/neuralops-nexus-backend](https://github.com/mapax-io/neuralops-nexus-backend) (uncheck "Copy only the main branch"), branch off `dev` as `feature/<name>` or `issue/<name>`, commit with the task ID in the message, open a PR against **`dev`** with a full description, then post it in Discord. See §3 above for getting the code running first.

> **Branch notice:** `dev` is the active development branch — clone and build from it. `master`/`main` may lag behind.

---

## 5. License

NeuralOps Nexus is licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0). See [`LICENSE.md`](./LICENSE.md) for the full text.

In short: you're free to use, modify, and self-host this software, but if you run a modified version as a network service, you must make your modified source available to that service's users. See §13 of the license for the specifics.
