# Open Items — deferred during the docs/repo reorg pass

Running notes on things flagged mid-cleanup but deliberately not fixed yet,
so they don't get lost. Add to this rather than fixing inline unless you say
otherwise.

---

## Dev nginx.conf doesn't block `/api/v1/internal/`

**Where:** root-level `nginx.conf` (dev profile, used by `docker-compose.yaml`'s
`dev` profile).

**What's different from production:** `neuralops/nginx.conf` (the unified-image
production config) explicitly returns 403 on `/api/v1/internal/`:

```
location /api/v1/internal/ {
    return 403;
}
```

The dev config has no equivalent block. `/api/v1/internal/` is meant to be
called only container-to-container (nexus-ai → nucleus) and, per the
production config's own comment, its endpoints return real secrets —
decrypted AI-model API keys, raw chat history. In the dev config, a request
to that path just falls through to the generic `/api/` location and gets
proxied straight to `nucleus-dev:8000`, protected only by the
`X-Internal-API-Key` header check on the Django side, not by a network-level
block the way production has it.

**Decision needed:** is this an acceptable gap for a local/dev-only setup, or
should the same `return 403` block be ported into the dev nginx.conf too?

---

## Centrifugo runs fully insecure — in production, not just dev

**Where:** two separate places, both currently insecure, in different ways:

- Root `centrifugo.json` (old dev profile): `"client_insecure": true`,
  `"allowed_origins": ["*"]`.
- `neuralops/entrypoint.sh`'s `centrifugo` mode (the CURRENT production /
  unified-image flow — this is what self-hosters actually run today):

  ```
  nexus-transport --admin.enabled --admin.insecure --client.insecure --http_api.insecure
  ```

This is baked directly into `entrypoint.sh`, not read from any JSON file —
`centrifugo.json` isn't used by the new Docker setup at all, only by the old
dev-profile `docker-compose.yaml`.

**Why it matters more than the earlier framing suggested:** this isn't just
the client-channel-isolation gap noted in `TASKS.md`'s gotchas
(`--client.insecure` — no per-channel JWT, channel isolation relies on
clients only subscribing to topics they were legitimately given). Production
also runs `--admin.insecure` (Centrifugo's admin panel, no auth) and
`--http_api.insecure` (the HTTP control API, no auth) wide open, by default,
on every current self-hosted deployment. nginx currently only proxies
`/connection/websocket` and `/connection/sse` — so the admin/HTTP API
surfaces aren't directly internet-reachable through nginx today, but they
are reachable to anything else that can reach the `centrifugo`/`realtime`
container directly (another container on the same network, or the host
itself if the port's published) — worth explicitly confirming that no
compose file publishes that port before treating this as low-risk.

**Decision needed:** whether to move to token-based client auth (the
"backlog task on adding a post-connect token endpoint" mentioned in
`neuralops/nginx.conf`'s own comment) and drop all three insecure flags
before this gets more real-world usage, and whether it's P0 or P1 —
`--client.insecure` requires a client to deliberately misbehave to matter,
but `--admin.insecure`/`--http_api.insecure` don't require misbehavior, just
network reachability.

---

## Rename `neuralops/` folder to `docker/`

**Where:** the `neuralops/` folder at repo root (`Dockerfile`, `entrypoint.sh`,
`infra.env.example`, `app.env.example`, `nginx.conf`, `nginx.dev.conf`) — the
unified-image build context for the current production self-host flow.

**Status:** deliberately deferred — decided not to do this now, revisit later.

**What the rename touches, so this doesn't get done half-way later:**

- The folder's own files move as a unit — no internal changes needed.
- `docker-compose.neuralops.yaml` (root) — build context/Dockerfile path and
  both env-file paths (`infra.env.example`, `app.env.example`) currently
  point at `neuralops/...` and would need updating.
- `neuralops/entrypoint.sh` — header comments reference the folder name
  (cosmetic, won't break anything, but will read wrong post-rename).
- `docs/SELF-HOST.md` — likely has setup instructions pointing at
  `neuralops/` for env files.
- `docs/DECISIONS.md` — §20's discussion of the unified-image flow likely
  names the folder.
- `readme.md` — if it walks through unified-image setup or links to files
  inside the folder.

**Decision needed when this is picked back up:** whether to just move the
folder and leave references broken for a later pass (same approach used for
the `docs/` consolidation), or move it and fix every reference in the same
pass. Also worth a quick grep for the literal string `neuralops/` across the
repo first, rather than relying on this list, since it wasn't exhaustively
searched.

---

## Shared default Postgres/Redis credentials, both exposed on host ports

**Where:** `docker-compose.neuralops.yaml`'s `postgres` and `redis` service
blocks (production profile), plus `neuralops/infra.env.example`.

**What's wrong:** `infra.env.example` ships literal example values —
`POSTGRES_DB=neuralops`, `POSTGRES_USER=neuralops`,
`POSTGRES_PASSWORD=change-me` — and unlike `FIELD_ENCRYPTION_KEY` /
`INTERNAL_API_KEY` / `CENTRIFUGO_API_KEY` / `CENTRIFUGO_HMAC_SECRET` (which
get a dedicated `init-secrets` generator producing a fresh random value per
deployment), there is no equivalent generator or forced-change mechanism for
the Postgres credentials. A self-hoster who copies the example file and
doesn't specifically go edit `POSTGRES_PASSWORD` ends up running Postgres
with the literal password `change-me` — confirmed this repo's own
`neuralops/infra.env` still has it unchanged.

Redis has the same shape of gap but worse: no `REDIS_PASSWORD` / Redis
`--requirepass` is set anywhere in the compose file or example env — Redis
runs with **zero authentication** at all, not even a shared default one.

**Why it's more than cosmetic:** both services publish host ports in the
`postgres`/`redis` blocks — `${POSTGRES_HOST_PORT:-5495}:5432` and
`${REDIS_HOST_PORT:-6395}:6379` — meaning they're not internal-network-only.
If a self-hoster's firewall, cloud security group, or tunnel/funnel config is
more permissive than intended, these ports are reachable from outside the
host. Combined with a widely-known shared default password (or no password
at all, for Redis), that turns "misconfigured firewall" into "anyone can
connect directly to the database or cache with `psql`/`redis-cli`,
bypassing the app layer and RBAC entirely."

**Decision needed:** whether Postgres credentials should get the same
per-deployment `init-secrets`-style generation treatment the other four
secrets already have; whether Redis should require a password by default;
and whether `postgres`/`redis` need their host `ports:` mappings published
at all in the production profile, versus staying reachable only over
`neuralops-network` internally (nothing outside the stack currently seems to
need direct host access to either).

---

## neuralops-react-app: 8 remaining eslint warnings

**Where:** `modules/neuralops-react-app` (`npm run lint`).

Left in place during the 2026-09 UI/build-fix pass because fixing them
changes behavior, not just style:

- 2× `react-hooks/exhaustive-deps` — `AddPersonaForm.tsx:87` (missing
  `projectId`), `useChat.ts:448` (missing `channelId`/`projectId`). Adding
  the deps re-runs those effects on channel/project switches; that needs a
  deliberate review of the intended reset semantics, not a mechanical fix.
- 6× `react-refresh/only-export-components` — shadcn/ui files exporting
  variants/helpers alongside components (`badge`, `button`, `form`,
  `navigation-menu`, `sidebar`, `toggle`). Standard shadcn layout; fixing
  means splitting files and touching many imports for dev-only HMR benefit.

---

## neuralops-web-app: intelligence EDIT dialogs lack attach & use

**Where:** `modules/neuralops-web-app` — `agents-tab.tsx` EditAgentDialog,
`personas-tab.tsx` EditPersonaDialog.

The 2026-09 create-flow rework gave the CREATE dialogs a ModelPicker with an
"attach & use" group and inline register/add dialogs. The edit dialogs still
use plain project-filtered selects: swapping an agent's model is limited to
models already attached to its project, with no inline attach or register.
Same treatment as create would close the gap.

## neuralops-web-app: Escape during an in-flight create still completes it

**Where:** `modules/neuralops-web-app` — all intelligence create dialogs.

Pre-existing semantics (predates the create-flow rework, which only widened
the window with the attach-first step): once submit fires, closing the dialog
does not abort the mutation — the entity is still created and toasts. If
cancel-on-close is ever wanted, it needs AbortSignal plumbing through the
mutations; today the toast at least announces the outcome.
