# Self-Hosting NeuralOps (unified image)

This is the fast path: **one pre-built Docker image**
(`noamanfaisal/neuralops`), no source code, no local builds. If you want a
developer setup instead, see `readme.md` §3 — there are two, and note that
*this same compose file* also carries a `dev` profile (builds the image
locally and bind-mounts source for hot-reload, but ships no frontend). The
older `docker-compose.yaml` `dev` profile is the one with a local React app;
that file is untouched by this guide.

There is **no local frontend** in this bundle. You sign in at the hosted
NeuralOps app and connect it to your self-hosted server's URL — see step 7.

This supersedes the older "fat" distribution (`docker-compose.yaml`'s `fat`
profile, three separate `neuralops-nucleus`/`neuralops-nexus-ai`/
`neuralops-nginx` images, `install.sh`). Same idea — pre-built images, no
source tree — but one shared image (`neuralops/Dockerfile`) now backs
`nucleus`, `nexus-ai`, and `centrifugo`, each still its own container,
selected via `entrypoint.sh`'s first argument. See the comment block at the
top of `docker-compose.neuralops.yaml` and `DECISIONS.md` §20 for the fuller
history (§20 documents the *fat* profile specifically; this file documents
what replaced it).

> **Confirmed against a live run.** Every step below — clone, secrets,
> `./projects` folder, bring-up, `migrate`/`create_owner`/`seed_permissions`,
> Tailscale Funnel — was walked through end-to-end on a real box, starting
> from an empty folder, before this doc was written up.

## Requirements

- Docker with the Compose v2 plugin.
- ~4GB RAM minimum. Can drop closer to 2GB if you use an API-based embedding
  provider instead of the default local `fastembed` model, which gets loaded
  fully into memory.
- An existing NeuralOps account (sign up at the hosted app first) — needed
  for `create_owner` in step 6.

## Step 1 — Get the compose file and env templates

```bash
mkdir neuralops-selfhost && cd neuralops-selfhost
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus-backend/dev/docker-compose.neuralops.yaml -o docker-compose.neuralops.yaml
mkdir -p neuralops
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus-backend/dev/neuralops/infra.env.example -o neuralops/infra.env
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus-backend/dev/neuralops/app.env.example -o neuralops/app.env
curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus-backend/dev/neuralops/nginx.conf -o neuralops/nginx.conf
```

> `neuralops/nginx.conf` is **required**, not optional — the `nginx` service
> bind-mounts it (`./neuralops/nginx.conf:/etc/nginx/nginx.conf:ro`). If the
> file isn't there, Docker silently creates a *directory* with that name and
> nginx dies on startup with `"/etc/nginx/nginx.conf" is a directory`. Verify
> with `test -f neuralops/nginx.conf && echo ok` before step 5.

> Both `neuralops/infra.env` and `neuralops/app.env` are gitignored templates
> you fill in locally — never commit real values.

## Step 2 — Generate your deployment's secrets

Five internal secrets (`FIELD_ENCRYPTION_KEY`, `INTERNAL_API_KEY`,
`CENTRIFUGO_API_KEY`, `CENTRIFUGO_HMAC_SECRET`, `POSTGRES_PASSWORD`) are
generated fresh per install — nothing shared with anyone else's deployment,
and nothing baked into the public image:

```bash
docker run --rm noamanfaisal/neuralops:0.1.2 init-secrets > neuralops/secrets.env
cat neuralops/secrets.env   # confirm 5 lines
```

`POSTGRES_PASSWORD` is in this list because `infra.env.example` used to ship
a literal example password with no generator — every self-hosted deployment
risked sharing the same credential, and Postgres also publishes a host port
(`POSTGRES_HOST_PORT`), so that wasn't just theoretical.

Safe to run again if you ever lose the file, but note: rotating these after
first run invalidates existing sessions and re-encrypts nothing automatically
(existing AI-model keys encrypted under the old `FIELD_ENCRYPTION_KEY` won't
decrypt, and Postgres won't accept a new `POSTGRES_PASSWORD` against an
already-initialized data volume) — treat `neuralops/secrets.env` as something
to generate once and keep, not regenerate casually.

## Step 3 — Create the project files folder

`nexus-ai`'s workspace (`/nexus/projects`) is a bind mount to `./projects` in
this folder, not a Docker-managed volume — so you can see, edit, and back up
your actual project files as a normal directory. It has to exist and be
owned by the container's non-root user (UID/GID 1000) *before* the first
`up`, or `nexus-ai` will fail to write into it:

```bash
mkdir -p ./projects
sudo chown -R 1000:1000 ./projects
```

Skipping this isn't fatal but is confusing: Compose auto-creates `./projects`
as root-owned if it's missing, and `nexus-ai` then fails with permission
errors the first time it tries to write a file — fixable after the fact by
running the same `chown` and restarting `nexus-ai`, but doing it up front
avoids hitting the failure at all.

## Step 4 — Fill in the two env files

`neuralops/infra.env` — the external plumbing:

| Variable | Purpose |
|---|---|
| `COMPOSE_PROJECT_NAME` | Already set to `neuralops` — **do not remove this line.** Without it, Compose scopes containers by directory name and can collide with an existing `docker-compose.yaml` dev/fat stack in the same folder (see the comment in `infra.env.example`). |
| `COMPOSE_PROFILES` | Already set to `production` — pulls prebuilt images, no build step. |
| `POSTGRES_DB` / `POSTGRES_USER` | Plain identifiers, not secrets — working defaults, safe to leave as-is or change for minor extra hardening. `POSTGRES_PASSWORD` is **not** set here anymore — it comes from `neuralops/secrets.env` (step 2). |
| `NGINX_HOST_PORT` / `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` / `NEXUS_AI_HOST_PORT` | Optional — defaults (8095/5495/6395/8020) are fine unless something else on the box already uses them. Only `NGINX_HOST_PORT` needs to be reachable from outside; see the port note below. |
| `NEURALOPS_IMAGE` | Optional — defaults to `noamanfaisal/neuralops:latest`. **Set it to a pinned tag** (e.g. `noamanfaisal/neuralops:0.1.2`) if you want upgrades to happen only when you choose, rather than on any `docker compose pull`. Use the same value in step 2's `init-secrets` command. |

> **Only expose `NGINX_HOST_PORT`.** The compose file also publishes Postgres
> (5495), Redis (6395), and nexus-ai (8020) to the host for debugging. Those
> bind to all interfaces, so on a public box put them behind a firewall or set
> them to loopback (e.g. `POSTGRES_HOST_PORT=127.0.0.1:5495`). `nexus-ai` in
> particular exposes unauthenticated `/`, `/health`, and
> `/api/v1/internal/providers` endpoints.

`neuralops/app.env` — the things that are genuinely different per deployment:

| Variable | Purpose |
|---|---|
| `NEURALOPS_SERVER_URL` | The URL *other people* will reach this server at, e.g. `https://neuralops.example.com` — not `localhost` unless you're the only user. Defaults to `http://localhost:8095`. |
| `CENTRIFUGO_ALLOWED_ORIGINS` | Centrifugo (the realtime service) reads this under its own name — set it to the **exact same value** as `NEURALOPS_SERVER_URL` above. Not derived automatically; keep both in sync whenever either changes. |

Both of these are loaded directly by `nucleus`/`centrifugo` via `env_file:`
in `docker-compose.neuralops.yaml`, so they take effect the moment the
container is (re)created — no special flag needed on the `up` command for
them specifically.

Everything else (portal URL, version) is baked into the image itself and
isn't settable from these files — see the comment block in
`neuralops/app.env.example` if you're curious why. The Supabase identity
project is the exception: the image bakes the shared platform project as the
default, and `SUPABASE_URL` / `SUPABASE_ANON_KEY` (plus the optional
`SUPABASE_SERVICE_KEY`, which turns on invitation emails) can be set in
`app.env` to run against your own project — the web app must then point at
the same project. There's also no AI
provider key here on purpose — you add that from inside the chat after
connecting (step 8), not as an env var.

## Step 5 — Bring the stack up

```bash
docker compose -f docker-compose.neuralops.yaml \
  --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
  up -d
```

`docker compose ... ps` should show 9 containers up: `nucleus`,
`nucleus-celery`, `nucleus-celery-beat`, `nexus-ai`, `centrifugo`, `postgres`,
`redis`, `chromadb`, `nginx`.

> Always pass all three `--env-file` flags together on every command below —
> Compose doesn't auto-load `neuralops/*.env`, and this repo's existing plain
> `.env` belongs to the *old* `docker-compose.yaml` (different profile names,
> would collide if picked up by accident).

## Step 6 — First-run setup

Run these once, in order, against a fresh database. `docker exec` bypasses
`entrypoint.sh` (the thing that normally puts the right venv on `PATH`), so
call the venv's Python binary by its full path instead:

```bash
docker exec -it neuralops-nucleus /opt/venv/nucleus-env/bin/python /nexus/nucleus/manage.py migrate
docker exec -it neuralops-nucleus /opt/venv/nucleus-env/bin/python /nexus/nucleus/manage.py create_owner
docker exec -it neuralops-nucleus /opt/venv/nucleus-env/bin/python /nexus/nucleus/manage.py seed_permissions
```

Order matters:

- `migrate` first — creates the schema.
- `create_owner` second — interactive, needs a **Supabase account already
  created at the NeuralOps sign-up page** (sign up first if you don't have
  one); creates the Company and grants you the Owner role.
- `seed_permissions` third — seeds the RBAC right codes for the Company
  `create_owner` just made. Skip it and every permission check 500s with
  `Unknown right code`. Safe to re-run if needed.

## Step 7 — Expose your server

Same two options as the old fat profile — pick one:

**Tailscale Funnel** (simplest, no router config):

```bash
curl -fsSL https://tailscale.com/install.sh | sh   # skip if already installed
sudo tailscale up                                    # skip if already logged in
sudo tailscale funnel --bg 8095                       # or your NGINX_HOST_PORT
```

Then, in `neuralops/app.env`, set **both** `NEURALOPS_SERVER_URL` and
`CENTRIFUGO_ALLOWED_ORIGINS` to the printed `https://...ts.net` URL (nucleus
builds the value into API responses; centrifugo checks it for allowed
WebSocket origins), and recreate the two services that read it:

```bash
docker compose -f docker-compose.neuralops.yaml --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
  up -d nucleus centrifugo
```

> Use `up -d`, not `restart` — env files are only read when a container is
> *created*. A plain `restart` reuses the container's existing environment
> and will silently keep the old URL. `up -d` recreates just the services
> whose config actually changed, so this is safe to run any time.

**Your own domain / reverse proxy / cloud load balancer** — point it at
`NGINX_HOST_PORT` on this machine, set both env vars above to match, and
recreate the same two services.

## Step 8 — Connect and add a model

1. Open the NeuralOps web app, choose "Connect to your own server," and
   enter your server's URL from step 7. Sign in with the account you just
   made the owner of.
2. In any chat, type `/add-model` and paste an OpenAI or Anthropic API key —
   it's stored encrypted per-row using `FIELD_ENCRYPTION_KEY` from
   `neuralops/secrets.env`, not read from any env var.

## Updating

```bash
docker compose -f docker-compose.neuralops.yaml --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env pull
docker compose -f docker-compose.neuralops.yaml --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env up -d
```

Data lives in the named `neuralops_*` volumes (Postgres, Redis, Chroma,
fastembed cache) plus the `./projects` folder from step 3 — untouched by
pulling a new image. Generate `neuralops/secrets.env` once, ever, per
deployment and keep it — don't regenerate it as part of a routine update
(see the note in step 2).

## Troubleshooting

- **"Unknown right code" 500** — `seed_permissions` hasn't run (step 6).
- **`ImproperlyConfigured` / encryption errors on first request** —
  `neuralops/secrets.env` wasn't generated or wasn't passed as an
  `--env-file`; see step 2.
- **`fe_sendauth: no password supplied` on `migrate`** — `secrets.env` is
  missing `POSTGRES_PASSWORD`, or Postgres's data volume was already
  initialized under a different password before you set this one (Postgres
  only reads `POSTGRES_PASSWORD` on first `initdb`, not on every restart).
  If the volume genuinely has no real data yet, the fix is a full reset:
  `down -v` then `up -d` again so Postgres reinitializes fresh against the
  current secrets.
- **`python: can't open file '/nexus/manage.py'`** — you ran
  `python manage.py ...` without the full path; `manage.py` lives at
  `/nexus/nucleus/manage.py`, not `/nexus/manage.py` (the container's
  `WORKDIR`). Use the full paths in step 6.
- **`ModuleNotFoundError: No module named 'django'` on `docker exec`** —
  `docker exec` bypasses `entrypoint.sh`, so the venv was never put on
  `PATH`. Call `/opt/venv/nucleus-env/bin/python` directly, as in step 6.
- **`nexus-ai` fails to write to its project files** — `./projects` wasn't
  created and chowned before the first `up` (step 3); Compose auto-created
  it as root-owned instead. Fix: `sudo chown -R 1000:1000 ./projects`, then
  `docker compose ... up -d nexus-ai`.
- **Can't log in / server unreachable from another device** —
  `NEURALOPS_SERVER_URL` (and `CENTRIFUGO_ALLOWED_ORIGINS`) in
  `neuralops/app.env` need to be the URL *other* machines can reach, not
  `localhost`. Recreate `nucleus` and `centrifugo` with `up -d` (not
  `restart`) after changing either one (step 7).
- **502 from nginx** — check `docker compose ... logs nginx`; usually means
  `nucleus` isn't up yet, or crashed — check `docker compose ... logs nucleus`.
- **Filesystem MCP / tool calls fail with connection refused** — MCP servers
  called from `nexus-ai` need your host's real IP, not `localhost` — same
  rule as the `dev` profile, see `readme.md`'s "Add an MCP server" section.

Full design rationale for the fat-profile predecessor of this stack:
`DECISIONS.md` §20.
