#!/usr/bin/env bash
# =============================================================================
# NeuralOps Nexus — one-command installer for Linux servers.
#
#   curl -fsSL https://raw.githubusercontent.com/mapax-io/neuralops-nexus/main/install.sh | bash
#
# What it does, in order (every step is safe to re-run):
#   1. checks the machine (Linux, x86_64, memory, disk), installs Docker if
#      missing (asks first);
#   2. asks ONE question — how the team reaches this server:
#        (1) a domain name  -> automatic HTTPS certificate (Caddy)
#        (2) no domain      -> a free secure address (Cloudflare quick tunnel)
#   3. downloads the compose file + nginx config, writes the env files,
#      generates this install's secrets ONCE (never regenerated — that would
#      replace the live database password), fixes the projects folder owner;
#   4. starts everything, creates the vector database, runs migrate +
#      seed_permissions + seed_catalog, waits until the server answers;
#   5. installs the `neuralops` command (status / update / logs / address /
#      backup / restart / stop / start / uninstall) and prints the address.
#
# Unattended use: set NEURALOPS_MODE=domain NEURALOPS_DOMAIN=team.example.com
# (or NEURALOPS_MODE=tunnel) and NEURALOPS_YES=1 — no questions are asked.
#
# Testing from a local checkout (no network fetch of the files):
#   NEURALOPS_RAW=file:///path/to/neuralops-nexus bash install.sh
#
# Record: docs/MISSING.md (Stage 4, easy install — ruled 2026-10-24).
# =============================================================================
set -euo pipefail

NEURALOPS_VERSION="${NEURALOPS_VERSION:-1.0.0}"
NEURALOPS_REF="${NEURALOPS_REF:-main}"
NEURALOPS_RAW="${NEURALOPS_RAW:-https://raw.githubusercontent.com/mapax-io/neuralops-nexus/${NEURALOPS_REF}}"
NEURALOPS_DIR="${NEURALOPS_DIR:-/opt/neuralops}"
NEURALOPS_IMAGE_REPO="${NEURALOPS_IMAGE_REPO:-noamanfaisal/neuralops}"
NEURALOPS_MODE="${NEURALOPS_MODE:-}"
NEURALOPS_DOMAIN="${NEURALOPS_DOMAIN:-}"
NEURALOPS_YES="${NEURALOPS_YES:-}"

MIN_MEM_KB=$((3500 * 1024))   # ~3.5 GB — the engine's ML stack needs room
MIN_DISK_KB=$((15 * 1024 * 1024))

# ── output ────────────────────────────────────────────────────────────────────
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n  \033[31m✘ %s\033[0m\n\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m▸ %s\033[0m\n' "$*"; }

# Questions read from the terminal, not stdin — stdin IS this script when it
# arrives through `curl | bash`.
ask() {  # ask "Question" "default" -> echoes the answer
  local question="$1" default="${2:-}" answer=""
  if [ -n "$NEURALOPS_YES" ] || [ ! -r /dev/tty ]; then
    printf '%s' "$default"; return
  fi
  if [ -n "$default" ]; then
    printf '  %s [%s]: ' "$question" "$default" > /dev/tty
  else
    printf '  %s: ' "$question" > /dev/tty
  fi
  read -r answer < /dev/tty || true
  printf '%s' "${answer:-$default}"
}
confirm() {  # confirm "Question" -> returns 0 on yes (default yes)
  local a
  a="$(ask "$1 (Y/n)" "y")"
  case "$a" in [Nn]*) return 1 ;; *) return 0 ;; esac
}

# ── privileges ────────────────────────────────────────────────────────────────
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "Please run this as root, or install sudo first."
  SUDO="sudo"
fi

DOCKER=""
docker_cmd() {
  if docker info >/dev/null 2>&1; then DOCKER="docker"; else DOCKER="$SUDO docker"; fi
}

# The compose invocation every step (and the `neuralops` helper) uses.
PROFILES=""
compose() {
  # shellcheck disable=SC2086  # $DOCKER is "docker" or "sudo docker" on purpose
  (cd "$NEURALOPS_DIR" && COMPOSE_PROFILES="$PROFILES" $DOCKER compose \
    -f docker-compose.neuralops.yaml \
    --env-file neuralops/infra.env --env-file neuralops/app.env --env-file neuralops/secrets.env \
    "$@")
}

fetch() {  # fetch <path-in-repo> <destination>
  curl -fsSL "$NEURALOPS_RAW/$1" -o "$2.tmp" || die "Could not download $1 from $NEURALOPS_RAW"
  mv "$2.tmp" "$2"
}

# ── 1. the machine ───────────────────────────────────────────────────────────
check_machine() {
  step "Checking this machine"
  [ "$(uname -s)" = "Linux" ] || die "NeuralOps installs on Linux servers only."
  case "$(uname -m)" in
    x86_64|amd64) ok "Linux, $(uname -m)" ;;
    *) die "This server is $(uname -m). NeuralOps currently ships for x86_64 (Intel/AMD) servers only." ;;
  esac

  local mem_kb disk_kb parent
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  if [ "$mem_kb" -lt "$MIN_MEM_KB" ]; then
    warn "This server has $((mem_kb / 1024)) MB of memory; NeuralOps wants at least 4 GB."
    confirm "Continue anyway?" || die "Stopped. Pick a server with 4 GB of memory or more."
  else
    ok "Memory: $((mem_kb / 1024 / 1024)) GB"
  fi

  parent="$(dirname "$NEURALOPS_DIR")"
  disk_kb="$(df -Pk "$parent" | awk 'NR==2 {print $4}')"
  if [ "$disk_kb" -lt "$MIN_DISK_KB" ]; then
    warn "Only $((disk_kb / 1024 / 1024)) GB free at $parent; NeuralOps wants at least 15 GB."
    confirm "Continue anyway?" || die "Stopped. Free up disk space first."
  else
    ok "Disk: $((disk_kb / 1024 / 1024)) GB free"
  fi
}

check_existing() {
  if [ -f "$NEURALOPS_DIR/neuralops/secrets.env" ]; then
    bold ""
    bold "  NeuralOps is already installed in $NEURALOPS_DIR."
    say "To upgrade it, run:   neuralops update"
    say "To see its address:   neuralops address"
    say "(Re-installing over it would risk its data, so this installer stops here.)"
    echo
    exit 0
  fi
}

ensure_docker() {
  step "Docker"
  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker is not installed. NeuralOps runs inside Docker."
    confirm "Install Docker now (official script from get.docker.com)?" || die "Stopped. Install Docker, then run this again."
    curl -fsSL https://get.docker.com | $SUDO sh >/dev/null || die "Docker installation failed."
    $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
  fi
  docker_cmd
  $DOCKER compose version >/dev/null 2>&1 || die "Docker is installed but 'docker compose' is missing. Install the Docker Compose plugin, then run this again."
  ok "$($DOCKER --version)"
}

# ── 2. how the team reaches it ───────────────────────────────────────────────
choose_access() {
  step "How will your team reach this server?"
  if [ -z "$NEURALOPS_MODE" ]; then
    say "1) I have a domain name pointing at this server"
    say "   (recommended: permanent address with automatic HTTPS)"
    say "2) I don't have a domain: give me a free secure address"
    say "   (good for trying it out; the address changes if the server restarts)"
    case "$(ask "Choose 1 or 2" "2")" in
      1) NEURALOPS_MODE="domain" ;;
      *) NEURALOPS_MODE="tunnel" ;;
    esac
  fi

  case "$NEURALOPS_MODE" in
    domain)
      if [ -z "$NEURALOPS_DOMAIN" ]; then
        NEURALOPS_DOMAIN="$(ask "Your domain (e.g. team.example.com)" "")"
      fi
      NEURALOPS_DOMAIN="${NEURALOPS_DOMAIN#http://}"
      NEURALOPS_DOMAIN="${NEURALOPS_DOMAIN#https://}"
      NEURALOPS_DOMAIN="${NEURALOPS_DOMAIN%%/*}"
      [ -n "$NEURALOPS_DOMAIN" ] || die "A domain is needed for option 1."
      if command -v ss >/dev/null 2>&1 && ss -ltn | awk '{print $4}' | grep -Eq '(^|:)(80|443)$'; then
        die "Something on this server already uses port 80 or 443 (another web server?). Stop it, or use option 2."
      fi
      PROFILES="production,https"
      SERVER_URL="https://$NEURALOPS_DOMAIN"
      ok "Domain: $NEURALOPS_DOMAIN (its DNS must point at this server for the certificate)"
      ;;
    tunnel)
      PROFILES="production,tunnel"
      SERVER_URL=""   # known once the tunnel is up
      ok "A free secure address will be created"
      ;;
    *) die "NEURALOPS_MODE must be 'domain' or 'tunnel'." ;;
  esac
}

# ── 3. files, env, secrets ───────────────────────────────────────────────────
prepare_files() {
  step "Preparing $NEURALOPS_DIR"
  local me
  me="$(id -u):$(id -g)"
  $SUDO mkdir -p "$NEURALOPS_DIR/neuralops" "$NEURALOPS_DIR/projects" "$NEURALOPS_DIR/backups"
  $SUDO chown "$me" "$NEURALOPS_DIR" "$NEURALOPS_DIR/neuralops" "$NEURALOPS_DIR/backups"
  chmod 700 "$NEURALOPS_DIR/backups"

  fetch docker-compose.neuralops.yaml "$NEURALOPS_DIR/docker-compose.neuralops.yaml"
  fetch neuralops/nginx.conf "$NEURALOPS_DIR/neuralops/nginx.conf"
  ok "Downloaded the compose file and nginx config"

  cat > "$NEURALOPS_DIR/neuralops/infra.env" <<EOF
# Written by install.sh — the installer's settings for this server.
COMPOSE_PROJECT_NAME=neuralops
NEURALOPS_IMAGE=${NEURALOPS_IMAGE_REPO}:${NEURALOPS_VERSION}
POSTGRES_DB=neuralops
POSTGRES_USER=neuralops
NEURALOPS_DOMAIN=${NEURALOPS_DOMAIN}
# nginx answers on this machine only: caddy / the tunnel front it.
NGINX_BIND=127.0.0.1
EOF
  # The helper reads these back; profiles travel in the shell, never relying
  # on an env file to pick them.
  cat > "$NEURALOPS_DIR/neuralops/install.conf" <<EOF
NEURALOPS_DIR=${NEURALOPS_DIR}
NEURALOPS_RAW=${NEURALOPS_RAW}
NEURALOPS_IMAGE_REPO=${NEURALOPS_IMAGE_REPO}
NEURALOPS_MODE=${NEURALOPS_MODE}
PROFILES=${PROFILES}
EOF
  write_app_env "${SERVER_URL:-http://localhost:8095}"

  # Secrets: generated ONCE. An existing file is never touched.
  if [ ! -f "$NEURALOPS_DIR/neuralops/secrets.env" ]; then
    # An old database volume WITHOUT its secrets file would refuse the new
    # password (postgres keeps the one it was created with) — stop and say so
    # rather than produce a half-working install.
    if $DOCKER volume inspect neuralops_neuralops_postgres_data >/dev/null 2>&1; then
      die "An earlier NeuralOps database exists on this machine, but its secrets file is gone, so it cannot be opened. If you don't need that data, remove it with:  $DOCKER volume rm neuralops_neuralops_postgres_data  and run this installer again."
    fi
    step "Downloading NeuralOps (a few GB the first time; this takes a few minutes)"
    $DOCKER pull "${NEURALOPS_IMAGE_REPO}:${NEURALOPS_VERSION}"
    ( umask 077
      $DOCKER run --rm "${NEURALOPS_IMAGE_REPO}:${NEURALOPS_VERSION}" init-secrets > "$NEURALOPS_DIR/neuralops/secrets.env.tmp" )
    grep -q '^SECRET_KEY=' "$NEURALOPS_DIR/neuralops/secrets.env.tmp" || die "Generating this install's secrets failed."
    mv "$NEURALOPS_DIR/neuralops/secrets.env.tmp" "$NEURALOPS_DIR/neuralops/secrets.env"
    ok "Generated this install's own secrets (kept in neuralops/secrets.env, never regenerated)"
  fi

  # The engine runs as UID 1000 and writes project files here.
  $SUDO chown -R 1000:1000 "$NEURALOPS_DIR/projects"
  ok "Projects folder ready"
}

write_app_env() {
  cat > "$NEURALOPS_DIR/neuralops/app.env" <<EOF
# Written by install.sh. The public address of THIS server.
NEURALOPS_SERVER_URL=$1
CENTRIFUGO_ALLOWED_ORIGINS=$1
EOF
}

# ── 4. start + first-run setup ───────────────────────────────────────────────
start_tunnel_first() {
  # The address must be known BEFORE nucleus starts (it is the server's public
  # URL), so the tunnel comes up alone first.
  step "Creating your free secure address"
  compose up -d --no-deps cloudflared >/dev/null
  local url=""
  for _ in $(seq 1 45); do
    url="$($DOCKER logs neuralops-cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true)"
    [ -n "$url" ] && break
    sleep 2
  done
  [ -n "$url" ] || die "The secure address did not come up. Check the server's internet access, then run this again."
  SERVER_URL="$url"
  write_app_env "$SERVER_URL"
  ok "Address: $SERVER_URL"
}

wait_for() {  # wait_for "what" seconds command...
  local what="$1" secs="$2"; shift 2
  for _ in $(seq 1 "$secs"); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  die "Timed out waiting for $what. See: neuralops logs"
}

first_run_setup() {
  step "Starting NeuralOps"
  compose up -d
  ok "Containers started"

  # shellcheck disable=SC2086  # $DOCKER is one or two words on purpose
  wait_for "the database" 120 $DOCKER exec neuralops-postgres pg_isready -U neuralops
  # shellcheck disable=SC2016,SC2086  # the $VARS expand inside the container, on purpose
  $DOCKER exec neuralops-postgres sh -c '
    psql -U "$POSTGRES_USER" -lqt | cut -d"|" -f1 | grep -qw nexus_vectors \
      || psql -U "$POSTGRES_USER" -q -c "CREATE DATABASE nexus_vectors"
    psql -U "$POSTGRES_USER" -d nexus_vectors -q -c "CREATE EXTENSION IF NOT EXISTS vector"
  ' >/dev/null
  ok "Database ready (with the vector store)"

  # shellcheck disable=SC2206  # $DOCKER is one or two words on purpose
  local manage=($DOCKER exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus /opt/venv/nucleus-env/bin/python manage.py)
  wait_for "the server process" 60 "${manage[@]}" check
  "${manage[@]}" migrate --noinput >/dev/null || die "Setting up the database tables failed. See: neuralops logs nucleus"
  "${manage[@]}" seed_permissions >/dev/null || die "Loading the permissions failed. See: neuralops logs nucleus"
  "${manage[@]}" seed_catalog >/dev/null || warn "The model catalog did not load; it refreshes by itself daily."
  ok "Database set up"

  # The workers may have started before the tables existed — restart them.
  compose restart nucleus nucleus-celery nucleus-celery-beat nexus-ai >/dev/null
  wait_for "the server to answer" 120 sh -c \
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8095/api/v1/projects/ | grep -Eq '^(401|403)$'"
  ok "Server is answering"
}

# ── 5. the helper command ────────────────────────────────────────────────────
install_helper() {
  step "Installing the 'neuralops' command"
  fetch neuralops/neuralops-cli.sh "$NEURALOPS_DIR/neuralops/neuralops-cli.sh"
  chmod 755 "$NEURALOPS_DIR/neuralops/neuralops-cli.sh"
  $SUDO ln -sf "$NEURALOPS_DIR/neuralops/neuralops-cli.sh" /usr/local/bin/neuralops
  ok "Try: neuralops status"

  # A quick-tunnel address changes when the server reboots: re-sync it at
  # boot so the server always knows its own current address.
  if [ "$NEURALOPS_MODE" = "tunnel" ] && command -v systemctl >/dev/null 2>&1; then
    $SUDO tee /etc/systemd/system/neuralops-address.service >/dev/null <<'UNIT'
[Unit]
Description=NeuralOps Nexus - re-sync the free tunnel address after boot
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 20
ExecStart=/usr/local/bin/neuralops address

[Install]
WantedBy=multi-user.target
UNIT
    $SUDO systemctl daemon-reload >/dev/null 2>&1 || true
    $SUDO systemctl enable neuralops-address.service >/dev/null 2>&1 || true
  fi
}

finish() {
  local url="$SERVER_URL"
  echo
  bold "  ┌────────────────────────────────────────────────────────────┐"
  bold "  │  ✅  NeuralOps Nexus is running                             │"
  bold "  └────────────────────────────────────────────────────────────┘"
  echo
  say "Your server address:   $url"
  if [ "$NEURALOPS_MODE" = "domain" ]; then
    say "(The HTTPS certificate is fetched on the first visit and can take a minute.)"
  fi
  echo
  say "Next:"
  say "  1. Open  https://neuralopsnexus.ai  and sign in (or create an account)."
  say "  2. Add a server and paste:  $url"
  say "  3. The app shows a short code. Claim the server with it; you become its owner."
  echo
  if [ "$NEURALOPS_MODE" = "tunnel" ]; then
    warn "This free address changes if the server restarts. Run 'neuralops address'"
    warn "to see the current one. For a permanent address, use a domain."
    echo
  fi
  say "Useful commands:  neuralops status | neuralops update | neuralops logs | neuralops backup"
  echo
}

main() {
  echo
  bold "  NeuralOps Nexus — installer (version $NEURALOPS_VERSION)"
  check_existing
  check_machine
  ensure_docker
  choose_access
  prepare_files
  if [ "$NEURALOPS_MODE" = "tunnel" ]; then start_tunnel_first; fi
  first_run_setup
  install_helper
  finish
}

main "$@"
