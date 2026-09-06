# =============================================================================
# neuralops/Dockerfile — the unified "neuralops" image.
#
# One image, three app processes: nucleus (Django), nexus-ai (FastAPI),
# centrifugo (compiled Go binary, aka nexus-transport). Each runs as its own
# compose service/container from this SAME image, selected at `docker run`/
# compose time via entrypoint.sh's first argument + a `command:` override —
# see docker-compose.neuralops.yaml.
#
# Deliberately NOT in this image: postgres, redis, chromadb, nginx (separate
# services using their official images — see docker-compose.neuralops.yaml),
# pgvector (chroma only, matches current main), the rest of nexus-mcp
# (SerpAPI/Odoo — separate docker/compose, added later).
#
# nucleus and nexus-ai get their OWN separate venvs (nucleus-env /
# nexus-ai-env) rather than one shared/merged environment — Django+pydantic 2
# (nucleus) and pydantic-ai-slim/litellm (nexus-ai) pin different transitive
# dependency versions; one shared site-packages risks one module's install
# silently breaking the other's. Small extra image weight, real reduction in
# "works differently depending on install order" risk.
#
# Build context is the REPO ROOT (not this directory) — every COPY below is
# rooted there so it can reach modules/nexus-nucleus, modules/nexus-ai, and
# modules/nexus-transport in one build. Build with:
#   docker build -f neuralops/Dockerfile -t neuralops:local .
# =============================================================================

# ── Stage 1: nucleus deps ────────────────────────────────────────────────────
FROM python:3.11-slim AS nucleus-builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential libpq-dev && \
  rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv/nucleus-env
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY modules/nexus-nucleus/docker/dev/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: nexus-ai deps ───────────────────────────────────────────────────
FROM python:3.11-slim AS nexus-ai-builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
  bash \
  git \
  curl \
  build-essential libpq-dev && \
  rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv/nexus-ai-env
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY modules/nexus-ai/docker/dev/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: centrifugo / nexus-transport binary ────────────────────────────
# Same build this repo already uses for modules/nexus-transport/Dockerfile —
# replicated here (not COPY --from an external image) so the whole neuralops
# image builds from one `docker build` with no separate image to pull first.
FROM golang:1.26-alpine AS transport-builder
RUN apk add --no-cache git
WORKDIR /app
COPY modules/nexus-transport/go.mod modules/nexus-transport/go.sum ./
RUN go mod download
COPY modules/nexus-transport/ .
ENV CGO_ENABLED=0
RUN go build -ldflags="-s -w -X 'github.com/centrifugal/centrifugo/v6/internal/build.Version=v6.6.2-nexus'" \
  -o nexus-transport .

# ── Stage 4: final image ─────────────────────────────────────────────────────
FROM python:3.11-slim AS final

RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates libpq-dev curl nodejs npm && \
  rm -rf /var/lib/apt/lists/*

# Filesystem MCP — installed globally at build time (not left to `npx` to
# fetch on first run), same reasoning as the old Fat-Docker image: works
# offline, starts instantly. This is the one MCP server baked into the
# image; the rest of nexus-mcp (SerpAPI, Odoo ERP) stays out, per plan.
RUN npm install -g @modelcontextprotocol/server-filesystem

ARG UID=1000
ARG GID=1000
RUN groupadd -g $GID nexus && useradd -m -u $UID -g $GID -s /bin/bash nexus
# No passwordless sudo here on purpose — this stage is what production runs.
# The existing dev Dockerfiles (modules/*/docker/dev/Dockerfile.*) grant the
# "ubuntu" user passwordless sudo for interactive convenience; not carrying
# that into an image meant to also run as the default production build.

# ── Baked-in values, common to every deployment ─────────────────────────
# Only genuinely shared, non-secret (or safe-to-be-public) values live here
# now. SUPABASE_URL/SUPABASE_ANON_KEY point at one real Supabase project
# every deployment's login flow shares -- not per-install secrets, and
# ANON_KEY is designed to be public (protected by Supabase RLS).
# NEURALOPS_PORTAL_URL/VERSION are just informational/fixed.
#
# NEURALOPS_VERSION is ONE number for the whole image on purpose: nucleus,
# nexus-ai, and centrifugo are built together in this same Dockerfile from
# the same COPY of the repo, so there's no such thing as a real deployed
# state where they're at different versions from each other -- one build,
# one tag, one version. This is also the exact string the frontend compares
# itself against (see modules/neuralops-react-app/src/lib/version.ts,
# COMPATIBLE_SERVER_VERSION) -- that parser expects a plain MAJOR.MINOR(.PATCH)
# string, so keep bumps here in sync with that file, and with
# NEURALOPS_IMAGE in neuralops/infra.env.example, every time this changes.
#
# Explicitly NOT baked here:
#   - NEURALOPS_SERVER_URL -- genuinely different per deployment (the
#     public URL THIS box is reachable at), stays required/user-supplied.
#   - OPENAI_API_KEY / ANTHROPIC_API_KEY -- no shared default, ever;
#     nucleus's /add-model flow stores each one encrypted per-row in the
#     DB instead.
#   - SUPABASE_SERVICE_KEY -- removed once this repo went public. It's a
#     full-admin key for the whole shared Supabase project (bypasses RLS,
#     full Auth Admin API), and traced usage showed nothing in the app
#     actually needs it: neither POST /api/v1/members/invite/
#     (members_services.py:send_invite) nor the /invite slash command
#     (team_services.py:invite_to_project) call authn/supabase.py's
#     invite_user_by_email() -- both just create a pending Invitation row
#     and leave the person to share the link manually. settings.py
#     already defaults it to "" via os.getenv(), so leaving it unset here
#     is safe.
#   - FIELD_ENCRYPTION_KEY / INTERNAL_API_KEY / CENTRIFUGO_API_KEY /
#     CENTRIFUGO_HMAC_SECRET -- used to be baked as one shared default
#     here too, but that stopped being safe once this image went public:
#     INTERNAL_API_KEY in particular gates nucleus's /api/v1/internal/
#     endpoints (decrypted AI-model API keys, raw chat history), which
#     nginx proxies under the same public /api/ prefix as everything else
#     -- a baked, publicly-known INTERNAL_API_KEY would let anyone with a
#     deployment's URL pull that data out. These four are now generated
#     fresh per deployment instead -- run
#     `docker run --rm <image> init-secrets > neuralops/secrets.env` once
#     per install (see entrypoint.sh's init-secrets mode), then pass that
#     file as a third --env-file alongside infra.env/app.env. Referenced
#     in docker-compose.neuralops.yaml via ${VAR} in each service that
#     needs it -- NOT set here, so there's no shared value to fall back to.
ENV SUPABASE_URL="https://xgfsxikypxjhqlutiepw.supabase.co" \
  SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhnZnN4aWt5cHhqaHFsdXRpZXB3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyNDg3MDcsImV4cCI6MjA5NzgyNDcwN30.2_OUNTHuKSeDJh6S-aUW16IqvDTmew8ZcFuKvFkt3Dk" \
  NEURALOPS_PORTAL_URL="https://neuralops-nexus-demo.mapax.io" \
  NEURALOPS_VERSION="0.1.2"

COPY --from=nucleus-builder /opt/venv/nucleus-env /opt/venv/nucleus-env
COPY --from=nexus-ai-builder /opt/venv/nexus-ai-env /opt/venv/nexus-ai-env
COPY --from=transport-builder /app/nexus-transport /usr/local/bin/nexus-transport
# NOTE: no /nexus/transport-version file -- modules/nexus-transport has no
# VERSION file at its root (checked, doesn't exist), unlike what the old
# Fat-Docker Dockerfile snippet assumed. Double-checked: no authn/versions.py
# or anything else in modules/nexus-nucleus reads a file at this path either
# (searched, no matches) -- safe to leave out, nothing depends on it.
RUN chmod +x /usr/local/bin/nexus-transport

# App code — baked in here (this is what makes the `production` compose
# profile self-contained, no source tree required). The `dev` compose
# profile bind-mounts modules/nexus-nucleus and modules/nexus-ai over these
# same paths at container start, shadowing this copy with live host source —
# same image either way, dev just overlays it.
COPY modules/nexus-nucleus/ /nexus/nucleus/
COPY modules/nexus-ai/ /nexus/ai/

# Shared project folders — filesystem MCP is pointed at a per-project
# subfolder here (see readme's MCP section); mounted as an external volume
# at /nexus/projects in compose so it survives image rebuilds/upgrades.
#
# /home/nexus/.cache is ALSO a named-volume mount target in compose
# (fastembed's model cache) -- pre-creating + chowning it here matters for
# the exact same reason /nexus/projects does: a named volume only inherits
# the image's ownership on first mount if the target directory already
# exists in the image. Without this, Docker auto-creates the mount point
# as root-owned and fastembed's HuggingFace download fails with
# "Permission denied" the first time nexus-ai actually tries to embed
# something -- confirmed, this is exactly the bug that was hit.
RUN mkdir -p /nexus/projects /nexus/logs/nucleus /nexus/logs/ai /home/nexus/.cache/fastembed && \
  chown -R nexus:nexus /nexus /home/nexus/.cache

COPY neuralops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER nexus
WORKDIR /nexus
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
