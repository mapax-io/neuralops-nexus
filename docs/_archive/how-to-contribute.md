# Contributing to NeuralOps Nexus Backend

First off, thank you for considering contributing to NeuralOps Nexus! It's people like you that make this system powerful.

This document outlines the standard workflow for contributing to the neuralops-nexus-backend repository, plus how to run a full local dev build from source. Please read through these guidelines completely before starting your work to ensure a smooth review and merge process.

---

## 📋 Step 1: Finding a Task

Before writing any code, you need to select an approved task.

Navigate to our official **Project Task Board**: [github.com/orgs/NeuralOPS-Nexus/projects/3](https://github.com/orgs/NeuralOPS-Nexus/projects/3).

Look for tasks that are marked as **"Ready to Do"**.

Ensure the task you select has **no pending dependencies**.

**Claiming a task:** leave a comment on the issue saying you'd like to work on it. Only maintainers (accounts with write access) can actually set the "Assignees" field, so a maintainer will assign it to you once you've commented — this usually happens within a day or two. Please wait for that assignment before starting, so two people don't end up duplicating the same work.

If an issue has been assigned to someone for **more than 2 weeks with no comment or draft PR**, it's considered stale — a maintainer may reopen it for someone else to claim. This isn't a penalty, it just keeps issues from sitting blocked when someone's plans changed.

Once you're assigned, move the card to **"In Progress"** on the Project board if the view has a Status field — makes it easy for everyone to see what's actively being worked on at a glance.

## 🍴 Step 2: Forking the Repository

We use a standard Fork-and-Pull workflow.

Go to the ([main repository](https://github.com/mapax-io/neuralops-nexus-backend)).

Click the "Fork" button in the top right corner.

**CRITICAL:** When the fork configuration screen appears, deselect the option that says "Copy only the main branch". We need you to have access to all branches (especially `dev`).

Complete the fork to your personal GitHub account.

## 💻 Step 3: Local Environment Setup

Now, clone your fork locally and link it back to the main repository to keep your code up to date.

Open your terminal and run the following commands (replace `<your-username>` with your actual GitHub username):

```bash
# 1. Clone your forked repository (we recommend cloning into a folder named 'neuralops')
git clone git@github.com:<your-username>/neuralops-nexus-backend.git neuralops

# 2. Navigate into the project directory
cd neuralops/

# 3. Add the original Mapax-io repository as the "upstream" remote
git remote add upstream https://github.com/mapax-io/neuralops-nexus-backend.git

# 4. Verify your remotes (you should see 'origin' pointing to your fork and 'upstream' pointing to mapax-io)
git remote -v
```

## 🐳 Step 4: Running the Stack Locally (dev profile)

This builds and runs every service from source with hot-reload — what you'll want while actively developing. (If you just want to *use* NeuralOps without touching the code, see the self-hosting guide in the root [`readme.md`](./readme.md) instead — that uses a single pre-built image and is much faster to get running.)

**Prerequisites:** Docker & Docker Compose, Git.

```bash
git checkout dev   # branch with the current dev-profile compose setup
cp .env.example .env
```

```bash
docker build -f modules/nexus-nucleus/docker/dev/Dockerfile.nexus-nucleus . --no-cache
docker build -t nexus-backend:5.0 -f modules/nexus-nucleus/docker/dev/Dockerfile.nexus-nucleus . --no-cache
docker build -t nexus-ai:2.0 -f modules/nexus-ai/docker/dev/Dockerfile.nexus-ai . --no-cache
```

`.env` is gitignored on purpose — `.env.example` is the git-tracked template every fresh clone starts from. `COMPOSE_PROFILES=dev` is already set in it, so a bare `docker compose up` selects the right profile with no `--profile`/`-f` flags needed. Edit `.env` and fill in the blank `DEV_*` values — `.env.example` documents each one inline, but at minimum:

| Variable | Purpose |
|---|---|
| `DEV_POSTGRES_USER` / `DEV_POSTGRES_PASSWORD` / `DEV_POSTGRES_DB` / `DEV_POSTGRES_URL` | Database credentials |
| `DEV_FIELD_ENCRYPTION_KEY` | Encrypts stored model API keys — generate with `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `DEV_INTERNAL_API_KEY` / `DEV_CENTRIFUGO_API_KEY` / `DEV_CENTRIFUGO_HMAC_SECRET` / `DEV_NEURALOPS_INSTALL_TOKEN` | Shared secrets — any random string, e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DEV_OPENAI_API_KEY` / `DEV_ANTHROPIC_API_KEY` | At least one, for your first AI model |
| `DEV_SUPABASE_SERVICE_KEY` | From your Supabase project settings → API (service_role key). `DEV_SUPABASE_URL`/`DEV_SUPABASE_ANON_KEY` are already filled in for you — those are public by design, safe to ship in a frontend bundle |
| `DEV_NEURALOPS_SERVER_URL` | The URL *other people* will use to reach your server, e.g. `http://192.168.1.90:8081` — defaults to `http://localhost:8081`, which only works for you locally |

Verify nothing required is still blank, then bring the stack up:

```bash
docker compose config      # confirm no ${DEV_...} shows up empty
docker compose up -d
```

`docker compose ps` should show all 9 `dev-*` containers up: `dev-nucleus`, `dev-celery`, `dev-redis`, `dev-nexus-ai`, `dev-transport`, `dev-nginx`, `dev-chroma`, `dev-postgres`, `dev-react-app`. Data persists in `./data/dev/`.

### First-run setup

Run these once, in order, against a fresh database:

```bash
docker compose exec nucleus-dev python manage.py migrate
docker compose exec nucleus-dev python manage.py create_owner
docker compose exec nucleus-dev python manage.py seed_permissions
docker compose exec nucleus-dev python manage.py seed_avatars     # optional — populates the avatar pool
```

- `migrate` creates the schema.
- `create_owner` is interactive. It needs a **Supabase account already created at the NeuralOps sign-up page** — if you don't have one yet it'll tell you to sign up first, then run the command again. Once verified, it creates your workspace and grants you the Owner role (full permissions; Admin/Member/Viewer groups are also created automatically for inviting others later).
- `seed_permissions` seeds the RBAC right codes (`project.list`, `project.create`, etc.). Skip this and every permission check 500s with `Unknown right code`.
- `seed_avatars` fetches a pool of DiceBear avatar images so new users/personas get one assigned automatically on creation.

Then open `http://<your-server-ip>:3003` in a browser. Both port 3003 (frontend) and whatever `DEV_NGINX_HOST_PORT` is set to (default `8081`, the API) need to be reachable from wherever your browser is — same LAN, or whatever router/firewall/VPN rule you use for the rest of this server.

### Exposing your dev server

You have two options, depending on whether you want to use the hosted frontend or run everything locally.

**Option A — Public URL via Tailscale (use with a hosted frontend, e.g. a Vercel deployment)**

```bash
# Install Tailscale and join your tailnet
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Expose nginx-dev (host port from DEV_NGINX_HOST_PORT, default 8081) publicly over HTTPS via Tailscale Funnel
sudo tailscale funnel --bg 8081
```

This gives you a public `https://<machine-name>.<your-tailnet>.ts.net` URL that proxies straight to `nginx-dev` → `nucleus-dev`. Set that as `DEV_NEURALOPS_SERVER_URL` in `.env`, then restart both `nucleus-dev` and `realtime-dev` — Centrifugo's allowed-origins check also reads this value:

```bash
docker compose restart nucleus-dev realtime-dev
```

Then open the frontend, sign in with your Supabase account, use the "add server" / connect flow, and paste your Tailscale Funnel URL. `tailscale funnel status` shows the active funnel; `tailscale funnel --bg 8081 off` (or `tailscale funnel reset`) tears it down.

**Option B — Fully local, no Tailscale (run backend + frontend together)**

`react-app-dev` is already part of the `dev` profile — it comes up automatically with `docker compose up -d`. Set `DEV_NEURALOPS_SERVER_URL=http://localhost:8081` (or your machine's LAN IP, e.g. `http://192.168.1.90:8081`) in `.env`, then `docker compose restart nucleus-dev realtime-dev`. Open `http://<host>:3003` directly in the browser — nothing leaves your machine/network.

To remap any host-side port, change the matching `DEV_*_HOST_PORT` variable in `.env` rather than editing `docker-compose.yaml` directly.

## 📐 Coding Standards

Before you touch code, read [`DECISIONS.md`](./DECISIONS.md) — it records product decisions and constraints that must **not** be changed without the owner's approval, and it's expected reading at the start of any session that touches the backend.

Beyond specific decisions, these are the standing principles the codebase is held to (see [`STORY.md`](./STORY.md) for the full reasoning behind each):

1. **Simple beats clever.** The invite flow broke every time it got more sophisticated. The simplest version that works is the right version.
2. **Never block HTTP with AI.** Every AI call goes through Celery — always async, no exceptions.
3. **Soft delete everything.** Nothing is hard-deleted; `is_active=False` / `deleted_at` instead, so actions stay reversible and auditable.
4. **Services layer handles decisions, API layer handles HTTP.** No business logic in views/routers — keep it in `services.py`.
5. **One server, one company.** Don't add multi-tenancy complexity — this is a self-hosted product, not a SaaS platform.
6. **Don't solve problems you don't have yet.** No email server configured by default? Don't design a flow that requires one.

> **No automated CI yet.** There's no lint/test pipeline running on PRs today — "write tests if applicable" below is on the honor system for now. If you'd rather write infrastructure than app code, standing up a basic GitHub Actions workflow (lint + whatever test suite exists per service) is itself a genuinely useful first contribution — open it on the Project board.

Commit messages follow the format in Step 6 below (feature/issue ID + descriptive summary) — that's the one commit-level convention that's enforced in review.

## 🌱 Step 5: Branching Strategy

Never work directly on `main` or `dev`. Always create a new branch for your work. We use a strict naming convention based on the type of task.

Create and checkout your branch based on the following patterns:

For New Features: `feature/<subtask-name>`

```bash
git checkout -b feature/user-auth-module
```

For Bug Fixes / Issues: `issue/<subtask-name>`

```bash
git checkout -b issue/fix-database-timeout
```

## 🛠 Step 6: Making Changes and Committing

Write your code, write tests if applicable, and ensure everything runs locally.

When committing your changes, your commit messages must be descriptive. Include the feature/issue ID, the name of the task, and relevant details.

```bash
# Stage your changes
git add .

# Commit with a detailed message
git commit -m "feat(ID-123): Implement user auth module. Added JWT validation in apps/auth.py and updated the base models."
```

## 🚀 Step 7: Pushing to Your Fork

Once your work is committed, push your branch to your forked repository (origin).

```bash
# Push your branch to origin and set the upstream tracking
git push -u origin <your-branch-name>
# Example:
git push -u origin feature/testchange-usman
```

After the push is successful, your terminal will usually output a direct link to create a Pull Request. It will look something like this:
`https://github.com/<your-username>/neuralops-nexus-backend/pull/new/<your-branch-name>`

## 📥 Step 8: Creating the Pull Request (PR)

Click the link provided in your terminal, or go to your GitHub fork to open the Pull Request.

**CRITICAL PR INSTRUCTIONS:**

Change the Destination Branch: By default, GitHub might try to merge into `main`. You **MUST** change the base branch to `dev` (the destination branch for all active development).

Detailed Description: **Do not leave the PR description blank**. You must write a full, detailed breakdown of your PR, including:

- What code/logic did you add or change?
- Which specific files were modified or created?
- Why was this approach taken?
- Any specific areas you want the reviewer to look at closely.

In the PR description, reference the issue it resolves with `Fixes #<issue-number>` or `Closes #<issue-number>` — GitHub links the two automatically, and the issue closes on merge.

Click the "Create Pull Request" button.

## 💬 Step 9: Code Review and Communication

Your work isn't done just because the PR is open!

A maintainer will review your code — tag it on the Project board and it'll get picked up. Be prepared to answer questions or make requested changes based on their feedback.

Once approved, a maintainer will merge your branch into `dev`.

Thank you for contributing! Let's build the Nucleus.
Noaman Faisal Bin Badar

---
