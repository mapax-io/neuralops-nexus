# NeuralOps Nexus — Easy Install: the detailed design

**Written 2026-10-25.** The engineering design for getting NeuralOps onto a machine with as little effort as possible:

- **Step 1 — the one-command installer** (`install.sh` + the `neuralops` command), for anyone installing NeuralOps on their own Linux machine or server.
- **Step 2 — one-click demo servers** (`neuralops-demo`), an operator tool **we** run to give a person who requested a demo their own NeuralOps on AWS, Google Cloud or Microsoft Azure.

Status markers: **BUILT** = exists in the repo · **TO BUILD** = designed here, not written yet · **DECISION** = needs the owner's ruling.

Record of rulings: docs/MISSING.md (Stage 4, top — "EASY INSTALL"). Owner's reason for all of it: *"this is the biggest blocker, that normal people wont even try it."*

**Who builds it (owner, 2026-10-25):** the owner's developer, from the work list in **docs/EASY-INSTALL-TASKS.md** (exact behaviour, files, proof per task). This document is the background and design.

---

# STEP 1 — The one-command installer

## 1.1 What the person types

```
curl -fsSL https://get.neuralopsnexus.ai | bash
```

- `curl -fsSL` downloads the script quietly and fails cleanly on an error (no half-downloaded script runs).
- `| bash` runs it. Questions are read from the keyboard (`/dev/tty`), not from the pipe — so asking works even though the script arrives through `curl`.
- `get.neuralopsnexus.ai` is a short address that redirects to the script in the public repo (see 1.13). Until it exists, the long address works: `https://raw.githubusercontent.com/mapax-io/neuralops-nexus/main/install.sh`.

**Careful users** (common among self-hosters) can download, read, then run:
```
curl -fsSL https://get.neuralopsnexus.ai -o install.sh
less install.sh
bash install.sh
```

## 1.2 Where it runs

| Supported | Not supported (clear message, stops) |
|---|---|
| Linux on Intel/AMD (x86_64) — Ubuntu 22.04/24.04, Debian 12 are the tested targets; other distributions that Docker's official script supports should work | ARM machines (Raspberry Pi, AWS Graviton, Apple Silicon VMs) — the NeuralOps image is built for x86_64 only today |
| A local machine (home/office) — reached through Tailscale | macOS, Windows (later: desktop installer) |
| A cloud server with a public address (AWS EC2, DigitalOcean, Hetzner, Contabo…) — reached through a domain | Container-only hosts such as RunPod pods — Docker cannot run inside them |

Minimums: **4 GB memory** (the AI engine's libraries need room), **15 GB free disk** (the image is a few GB; data grows). Below either, the installer warns and asks whether to continue anyway.

## 1.3 The files involved

**In the repo (fetched by the installer at install time):**

| Repo path | Role | Status |
|---|---|---|
| `install.sh` | The installer itself | BUILT (v1) |
| `neuralops/neuralops-cli.sh` | The `neuralops` command | BUILT (v1) |
| `docker-compose.neuralops.yaml` | The stack (production profile + `https` profile) | BUILT — safety fixes included |
| `neuralops/nginx.conf` | The internal web server's routing | unchanged |

**On the server, after installing (default folder `/opt/neuralops`):**

```
/opt/neuralops/
├── docker-compose.neuralops.yaml      downloaded
├── neuralops/
│   ├── nginx.conf                     downloaded
│   ├── infra.env                      written: project name, image version, DB names, domain, NGINX_BIND
│   ├── app.env                        written: this server's public address
│   ├── secrets.env                    generated ONCE (mode 600) — never regenerated
│   ├── install.conf                   written: what the `neuralops` command needs to know
│   ├── .installed                     TO BUILD: written only when the install fully finished
│   └── neuralops-cli.sh               downloaded; /usr/local/bin/neuralops links here
├── projects/                          the files personas create (owner: UID 1000)
└── backups/                           `neuralops backup` output (mode 700)
```

Docker volumes (data that survives updates): `neuralops_neuralops_postgres_data`, `neuralops_neuralops_redis_data`, `neuralops_neuralops_fastembed_cache`, and for domain installs `neuralops_neuralops_caddy_data` / `neuralops_neuralops_caddy_config` (the HTTPS certificates).

## 1.4 Settings (all optional — for testing and for Step 2's unattended use)

| Variable | Default | Meaning |
|---|---|---|
| `NEURALOPS_VERSION` | `1.0.0` | Which release to install |
| `NEURALOPS_REF` | `main` | Which branch/tag of the repo to fetch files from |
| `NEURALOPS_RAW` | GitHub raw URL of mapax-io/neuralops-nexus at `NEURALOPS_REF` | Where files are fetched from. `file:///path/to/clone` tests from a local checkout |
| `NEURALOPS_DIR` | `/opt/neuralops` | Install folder |
| `NEURALOPS_IMAGE_REPO` | `noamanfaisal/neuralops` | Docker image name |
| `NEURALOPS_MODE` | (asked) | `tailscale` or `domain` — skips the question |
| `NEURALOPS_DOMAIN` | (asked) | The domain, for `domain` mode |
| `NEURALOPS_TS_REACH` | `funnel` | TO BUILD — `funnel` (anyone with the link, the ruled default) or `serve` (only your Tailscale devices) |
| `NEURALOPS_TS_AUTHKEY` | (none) | TO BUILD — a Tailscale auth key, for unattended Tailscale installs (no login link) |
| `NEURALOPS_YES` | (empty) | `1` = never ask; take every default (unattended) |

Example unattended install (what Step 2 uses):
```
curl -fsSL https://get.neuralopsnexus.ai | NEURALOPS_YES=1 NEURALOPS_MODE=domain NEURALOPS_DOMAIN=demo-x7k2.neuralopsnexus.ai bash
```

## 1.5 The flow, step by step

Every step prints one line (`✔` done, `!` warning, `✘` stopped with the reason). Nothing is shown that the person must understand to continue.

### Step 0 — Already installed? (resume-aware — TO BUILD)
- If `/opt/neuralops/neuralops/.installed` exists → prints *"NeuralOps is already installed. To upgrade: `neuralops update`"* and stops. Re-installing over a working install never happens.
- If `secrets.env` exists **but `.installed` does not** → a previous attempt stopped half-way. The installer **resumes**: keeps the existing secrets (never regenerates), and continues from the start of Step 4.
  *(v1 today stops in both cases — the resume behaviour is part of the rework.)*

### Step 1 — Check the machine
- Linux? Else: *"NeuralOps installs on Linux servers only."*
- x86_64? Else: *"This server is aarch64. NeuralOps currently ships for x86_64 (Intel/AMD) servers only."*
- Memory ≥ ~3.5 GB? Else warns and asks *"Continue anyway? (Y/n)"*.
- Free disk ≥ 15 GB where `/opt/neuralops` will live? Else warns and asks.

### Step 2 — Docker
- `docker` missing → *"Install Docker now (official script from get.docker.com)? (Y/n)"* → runs `curl -fsSL https://get.docker.com | sudo sh` and enables the Docker service.
- `docker compose` missing → stops with *"Install the Docker Compose plugin, then run this again."*
- Uses `docker` directly if the user may, otherwise `sudo docker`.

### Step 3 — How NeuralOps will be reached (the ONE question)
```
How will you reach NeuralOps?
  1) Tailscale (recommended for a machine at home or in the office)
     a permanent secure address; needs a free Tailscale account
  2) I have a domain (for a cloud server with a public address)
     automatic HTTPS certificate
```
Details of each path: 1.6 and 1.7.
*(v1 today offers "domain" and a Cloudflare quick tunnel; the rework replaces the tunnel with Tailscale — the quick tunnel's address changed on every restart.)*

### Step 4 — Prepare the files
1. Creates `/opt/neuralops/{neuralops,projects,backups}`.
2. Downloads `docker-compose.neuralops.yaml` and `neuralops/nginx.conf` (each to a `.tmp` file, then renamed — a failed download never leaves a broken file).
3. Writes `infra.env`:
   ```
   COMPOSE_PROJECT_NAME=neuralops
   NEURALOPS_IMAGE=noamanfaisal/neuralops:1.0.0
   POSTGRES_DB=neuralops
   POSTGRES_USER=neuralops
   NEURALOPS_DOMAIN=<domain, domain mode only>
   NGINX_BIND=127.0.0.1
   ```
4. Writes `install.conf` (folder, fetch source, image name, mode, compose profiles) for the `neuralops` command.
5. Writes `app.env` with the server's public address (filled in once known).
6. **Secrets** — only if `secrets.env` does not exist:
   - **Safety check:** if an old NeuralOps database volume exists without a secrets file, it stops: *"An earlier NeuralOps database exists on this machine, but its secrets file is gone … remove it with `docker volume rm neuralops_neuralops_postgres_data` and run this installer again."* (Postgres keeps the password it was created with — new secrets would be refused. Lesson from 2026-10-24.)
   - Pulls the NeuralOps image (*"a few GB the first time"*).
   - Runs the image's `init-secrets` → writes `secrets.env` with mode 600: `FIELD_ENCRYPTION_KEY`, `INTERNAL_API_KEY`, `CENTRIFUGO_API_KEY`, `CENTRIFUGO_HMAC_SECRET`, `POSTGRES_PASSWORD`, `SECRET_KEY`.
   - Verifies the file contains `SECRET_KEY` before keeping it.
7. Gives `projects/` to UID 1000 (the app's user) — the root-owned-folder lesson.

### Step 5 — Start and set up
1. `docker compose up -d` with the right profiles — pulls postgres (pgvector), redis, nginx, and Caddy for domain installs.
2. Waits for the database (`pg_isready`, up to 2 minutes).
3. Creates the vector store if missing: database `nexus_vectors` + `CREATE EXTENSION IF NOT EXISTS vector`.
4. Waits for the app container (`manage.py check`).
5. `manage.py migrate --noinput` → `manage.py seed_permissions` → `manage.py seed_catalog` (catalog failure is only a warning — it refreshes daily by itself).
6. Restarts nucleus, the two workers and the AI engine (they may have started before the tables existed).
7. Health check: `http://localhost:8095/api/v1/projects/` must answer 401/403 ("not signed in" — proves nginx + the app are alive), up to 2 minutes.
8. TO BUILD: writes `.installed` — the install counts as finished only now.

### Step 6 — The `neuralops` command
Downloads `neuralops/neuralops-cli.sh`, links it as `/usr/local/bin/neuralops`. Details: 1.9.

### Step 7 — The final box
```
  ┌────────────────────────────────────────────────────────────┐
  │  ✅  NeuralOps Nexus is running                             │
  └────────────────────────────────────────────────────────────┘

  Your server address:   https://myserver.tail1234.ts.net

  Next:
    1. Open  https://neuralopsnexus.ai  and sign in (or create an account).
    2. Add a server and paste:  https://myserver.tail1234.ts.net
    3. The app shows a short code. Claim the server with it; you become its owner.

  Useful commands:  neuralops status | neuralops update | neuralops logs | neuralops backup
```

## 1.6 Path 1 — Tailscale (TO BUILD)

Why: a local machine sits behind a router; nobody outside can reach it. Tailscale gives it a permanent HTTPS address — exactly how node3 runs today (`https://node-3.tail9ed39a.ts.net`).

**What the installer does:**
1. Installs Tailscale if missing: `curl -fsSL https://tailscale.com/install.sh | sh`.
2. Connects the machine to the person's Tailscale account:
   - **Interactive:** `tailscale up --hostname=neuralops` → Tailscale prints a login link → the installer shows it in a box: *"Open this link on your phone or laptop and sign in to your free Tailscale account"* → waits until the machine shows as connected.
   - **Unattended:** `tailscale up --authkey=$NEURALOPS_TS_AUTHKEY --hostname=neuralops` (no link).
3. Publishes NeuralOps:
   - **Funnel** (anyone with the link): `tailscale funnel --bg 8095` → `https://<machine>.<tailnet>.ts.net` forwards to nginx on `127.0.0.1:8095`. The first time on an account, Tailscale prints a second link to allow Funnel — the installer shows it the same way and waits.
   - **Serve** (only the person's own Tailscale devices): `tailscale serve --bg 8095`.
   - **RULED (owner, 2026-10-25): Funnel is the default** — teammates then install nothing; `serve` stays available as a setting.
4. Reads the address from `tailscale status --json` (the machine's own DNS name, trailing dot removed) → writes it into `app.env`.
5. Tailscale runs **on the machine itself** (not in a container): it already starts at boot, and the address never changes — no re-sync needed.

**Compose for this path:** profile `production` only (no Caddy). nginx stays bound to `127.0.0.1:8095`; Tailscale on the same machine reaches it.

**Failure messages:** login link not used within a few minutes → *"Waiting for the Tailscale sign-in timed out. Run the installer again; it will continue where it stopped."* (relies on the resume behaviour).

## 1.7 Path 2 — A domain (BUILT)

Why: a cloud server already has a public address; it only needs HTTPS, because the web app at neuralopsnexus.ai is HTTPS and browsers refuse to let it talk to a plain-HTTP server.

**What the installer does:**
1. Asks for the domain (e.g. `team.example.com`), strips any `https://` or path.
2. Checks ports 80 and 443 are free (another web server → stops with a clear message).
3. Turns on compose profile `https` → the `caddy` service: `caddy reverse-proxy --from <domain> --to nginx:80`, ports 80 + 443 published. Caddy fetches and renews a Let's Encrypt certificate by itself, and passes websockets through.
4. The address `https://<domain>` goes into `app.env`.

**The person must:** point the domain's DNS (an A record) at the server's public IP before or right after installing. Caddy retries until DNS is right.

## 1.8 The compose file (production side)

| Service | Image | Profile | Restart | Host port | Notes |
|---|---|---|---|---|---|
| nucleus | neuralops | production | unless-stopped ✱ | — | Django API |
| nucleus-celery | neuralops | production | unless-stopped | — | worker |
| nucleus-celery-beat | neuralops | production | unless-stopped | — | scheduler |
| nexus-ai | neuralops | production | unless-stopped ✱ | — | AI engine; no outside access by design |
| centrifugo | neuralops | production | unless-stopped ✱ | — | realtime |
| postgres | pgvector/pgvector:0.8.7-pg17 | production | always | `127.0.0.1:5495` ✱ | DB + vector store |
| redis | redis:7-alpine | production | unless-stopped | `127.0.0.1:6395` ✱ | no password — local only |
| nginx | nginx:alpine | production | unless-stopped | `${NGINX_BIND}:8095` ✱ | installer sets 127.0.0.1 |
| caddy | caddy:2-alpine | https | unless-stopped | 80, 443 | domain path only |
| cloudflared | cloudflare/cloudflared | tunnel | unless-stopped | — | v1 only — **removed in the rework** |

✱ = changed 2026-10-24. Before: the app had no restart policy (stayed down after a reboot), and Postgres + Redis were open to the internet on any VPS (Docker's published ports bypass the server's firewall).

## 1.9 The `neuralops` command (BUILT, Tailscale-aware in the rework)

| Command | What it does |
|---|---|
| `neuralops status` | Shows every container's state, the address, the version |
| `neuralops address` | Prints the address (Tailscale: from `tailscale status`; domain: from `app.env`) |
| `neuralops update [version]` | 1) makes a backup, 2) downloads the latest compose file, nginx config and itself, 3) sets the image version (default `latest`), 4) pulls and restarts, 5) runs the database setup (vector store, migrate, seeds), 6) swaps in the new copy of itself last |
| `neuralops backup` | Into `backups/neuralops-<date-time>/`: `database.sql.gz` (pg_dumpall — both databases and roles), `secrets.env` (needed: stored model keys are encrypted with it), `projects.tar.gz`. Warns that the backup holds secrets |
| `neuralops logs [service]` | Follows the logs (all, or e.g. `nucleus`, `nexus-ai`) |
| `neuralops restart` / `stop` / `start` | As named |
| `neuralops uninstall` | Asks to confirm → removes the containers, keeps all data. Then: *"ALSO delete ALL data? Type DELETE to confirm"* → only then removes the data volumes **by name**, the folder and the command. Never `docker compose down -v` |

Restore from a backup is not in the command yet — it is the Stage 4 backup & restore item.

## 1.10 Safety rules built in

1. Secrets are generated once, never regenerated, stored with mode 600; backups folder mode 700.
2. The database and Redis listen on the machine only; nginx too when Caddy or Tailscale fronts it.
3. Data is never deleted without the person typing `DELETE`; volumes are removed by name only.
4. Running the installer again never damages an install (stops, or resumes a half-finished one).
5. Every download goes to a temporary file first.
6. `update` always backs up before changing anything.

## 1.11 What changes in the rework (Step 1 remaining work)

1. **Tailscale path** (1.6) replaces the Cloudflare quick tunnel; `cloudflared` service removed from compose; the boot-time address re-sync unit is no longer needed and is dropped.
2. **Resume behaviour** with the `.installed` marker (Step 0).
3. `neuralops address` / `status` read the Tailscale address.
4. The question text becomes the two-choice version in Step 3.
5. Lint (shellcheck) clean again; then the proof runs (1.12).

## 1.12 Proof runs (owner)

| # | Machine | Path | Checks |
|---|---|---|---|
| P1 | A local Linux machine (fresh, or a VM) | Tailscale | install finishes · address opens in the hosted app · claim · create a project · a persona replies |
| P2 | A fresh cloud VPS | Domain | same, plus the certificate is valid |
| P3 | Either | — | run the installer again → it stops with "already installed" |
| P4 | Either | — | reboot the machine → NeuralOps comes back by itself, same address |
| P5 | Either | — | `neuralops backup` → three files exist · `neuralops update` → still works, data kept |
| P6 | Either | — | `neuralops uninstall` → keep data → `neuralops start` brings it back |

## 1.13 The short address `get.neuralopsnexus.ai`

A redirect on Vercel (where neuralopsnexus.ai already lives): a tiny project (or a rule in the existing one) for the host `get.neuralopsnexus.ai`:
```json
{
  "redirects": [
    { "source": "/", "destination": "https://raw.githubusercontent.com/mapax-io/neuralops-nexus/main/install.sh", "permanent": false }
  ]
}
```
plus a DNS record `get` pointing at Vercel. `curl -fsSL` follows the redirect. (Exact setup handed over when Step 1 passes its proof runs.)

---

# STEP 2 — One-click demo servers (hosted by us)

## 2.1 The answer in one line

**Yes — one script, `neuralops-demo`, with three cloud back-ends: AWS, Google Cloud, Microsoft Azure.** We run it; the person never touches it. Every back-end does the same five things — create a server, give it an address, install NeuralOps on it (the Step 1 installer, unattended), make the requester its owner, and delete it when the demo ends.

## 2.2 What the requester experiences

1. They request a demo on neuralopsnexus.ai (the existing Book-a-demo page / cal.com booking) and give their email.
2. A few minutes after we click, they receive a link: `https://demo-x7k2.neuralopsnexus.ai`.
3. They open neuralopsnexus.ai, sign in with **that email**, add the server — and they are already its **owner**: no code, no setup.
4. They use it for the demo period (**DECISION:** 1 hour, or longer). Then it disappears.

## 2.3 What we do

```
neuralops-demo create --cloud aws --email person@company.com --hours 1
```
…and it prints the link when the server is ready. Other commands:

| Command | What it does |
|---|---|
| `neuralops-demo create --cloud aws\|gcp\|azure --email E [--hours N]` | Create a demo for E |
| `neuralops-demo list` | All running demos, every cloud: id, email, address, time left |
| `neuralops-demo extend <id> --hours N` | Give a demo more time |
| `neuralops-demo delete <id>` | Delete now (server + address + AI key) |
| `neuralops-demo reap` | Delete every demo past its end time (runs automatically, see 2.9) |

Where it runs: on one of **our** machines (node3, or a small always-on box) that has the three cloud command-line tools installed and logged in with demo-only credentials.

## 2.4 The flow inside `create`

1. **Pick an id:** `d-x7k2` (short, random). Address: `demo-x7k2.neuralopsnexus.ai`. End time: now + N hours.
2. **Check the limit:** refuses if the maximum number of demos is already running (**DECISION:** e.g. 10) — protects the credits.
3. **Make a demo AI key** (if demos come with a working model — **DECISION**): a key with a **hard spending limit**, created through the provider's API (e.g. OpenRouter's key provisioning), named after the demo id.
4. **Write the first-boot file** (cloud-init, 2.6) — installer settings, the requester's email, the AI key.
5. **Create the server** on the chosen cloud (2.5), tagged `neuralops-demo=d-x7k2`, `expires=<end time>`, `owner-email=<email>`.
6. **Create the address:** as soon as the cloud reports the server's public IP, an `A` record `demo-x7k2.neuralopsnexus.ai → <IP>` in our DNS (**DECISION:** where the neuralopsnexus.ai DNS is managed — Vercel DNS or Cloudflare; both have an API).
7. **Wait until ready:** polls `https://demo-x7k2.neuralopsnexus.ai/api/v1/projects/` until it answers 401 (installed, certificate issued, app alive). Shows progress.
8. **Print the link** and a ready-to-send message for the requester (**DECISION:** we email it ourselves, or the script sends it).

## 2.5 The three cloud back-ends

Each back-end is a small file with the same four functions: `create`, `public_ip`, `delete`, `list`. Server size: the **4 GB memory class** on each cloud, **30 GB disk**, **Ubuntu 24.04**, firewall open only for **80 and 443**.

### AWS
```
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --instance-type t3.medium \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30}' \
  --security-group-ids <sg-demo: 80,443 only> \
  --user-data file://cloud-init.yaml \
  --instance-initiated-shutdown-behavior terminate \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=neuralops-demo,Value=d-x7k2},{Key=expires,Value=<end>}]'
```
- **Built-in self-destruct:** the first-boot file schedules `shutdown -h +<minutes>`; with `shutdown-behavior terminate`, AWS deletes the server itself at the end — even if our reaper is down.
- Delete: `aws ec2 terminate-instances --instance-ids <id>`.

### Google Cloud
```
gcloud compute instances create d-x7k2 \
  --machine-type e2-medium \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size 30GB \
  --tags neuralops-demo-web \
  --metadata-from-file user-data=cloud-init.yaml \
  --labels neuralops-demo=d-x7k2,expires=<end> \
  --max-run-duration <N>h --instance-termination-action DELETE
```
- **Built-in self-destruct:** `--max-run-duration` + `DELETE` — Google deletes the server at the end by itself.
- Firewall: one rule allowing 80/443 to the `neuralops-demo-web` tag (created once).
- Delete: `gcloud compute instances delete d-x7k2 --quiet`.

### Microsoft Azure
```
az group create -n rg-d-x7k2 -l <region> --tags neuralops-demo=d-x7k2 expires=<end>
az vm create -g rg-d-x7k2 -n d-x7k2 \
  --image Ubuntu2404 --size Standard_B2s --os-disk-size-gb 30 \
  --custom-data cloud-init.yaml --public-ip-sku Standard \
  --admin-username demo --generate-ssh-keys
az vm open-port -g rg-d-x7k2 -n d-x7k2 --port 80,443
```
- **One resource group per demo:** deleting the group removes the server, its disk, its address and its network together — nothing left behind costing money.
- No built-in self-destruct → relies on the reaper (2.9) — plus the first-boot file shuts the machine down at the end time as a backstop.
- Delete: `az group delete -n rg-d-x7k2 --yes --no-wait`.

*(Image names and sizes are checked against each cloud at build time — clouds rename them over time.)*

## 2.6 The first-boot file (cloud-init) — the same on all three clouds

```yaml
#cloud-config
runcmd:
  # 1. Install NeuralOps, unattended, with the demo's own address (Step 1 installer)
  - curl -fsSL https://get.neuralopsnexus.ai | NEURALOPS_YES=1 NEURALOPS_MODE=domain NEURALOPS_DOMAIN=demo-x7k2.neuralopsnexus.ai bash
  # 2. Reserve ownership for the requester (new create_owner mode, 2.7)
  - docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus /opt/venv/nucleus-env/bin/python manage.py create_owner --email person@company.com
  # 3. Demo content + the demo AI model (if ruled, 2.8)
  - docker exec ... manage.py seed_demo --model-key <demo key>
  # 4. Backstop: switch off at the end time even if everything else fails
  - shutdown -h +60
```
No SSH is needed at any point — the server sets itself up from this file.

## 2.7 New: `create_owner --email` (TO BUILD — nucleus)

**Today:** `create_owner` makes the first owner only through the person themselves — they type a code at the portal (or enter their own password with `--manual`). We cannot do that for them.

**New mode:** `manage.py create_owner --email person@company.com`
- Records that this server is **reserved for that email** (a pending owner).
- The first sign-in whose identity is **verified by the portal (Supabase) with that exact email** completes the claim — the same `claim_install` path as today (company, owner role, groups, rights). Anyone else trying to claim is refused.
- Refuses if the server already has an owner.
- Tests: reserved email claims → owner · different email → refused · unverified email → refused · second claim after the first → refused · reservation shows in `server_needs_owner` checks.

## 2.8 Demo content (DECISION)

Option A — **empty workspace + a ready AI model**: they start from zero, but chatting works immediately.
Option B — **a ready team**: a sample project, two or three personas (one with tools), a sample chain — they see the product's best side within a minute. Needs a small new `seed_demo` command.
Either way, the demo AI key has a hard spending limit and is revoked at deletion.

## 2.9 Deleting demos — three layers, so nothing is ever forgotten

1. **The reaper:** `neuralops-demo reap` runs every few minutes (a timer on our machine), finds demos past their `expires` tag on all three clouds, and deletes server + DNS record + AI key.
2. **The cloud's own self-destruct** where it exists (AWS terminate-on-shutdown, Google max-run-duration).
3. **The server switches itself off** at the end time (backstop for Azure).
Plus: **budget alerts** on each cloud account, so any surprise cost is visible immediately.

## 2.10 Security

- A **separate account / project / subscription for demos** on each cloud — demo credentials can touch nothing else.
- Credentials with only the permissions the script needs (create/delete servers, firewall, tags).
- Firewall: 80/443 only; no SSH open to the internet.
- Each demo is a throwaway server: whatever a persona does there stays there and disappears at the end.
- The demo AI key is readable inside the demo (the owner has shell tools via personas) — acceptable because it is capped and revoked at deletion.

## 2.11 What Step 2 needs, in order

1. **Free cloud credits** (owner): Microsoft for Startups Founders Hub, Google for Startups, AWS Activate — need the company incorporated. We build the back-end for whichever approves first; the other two follow the same pattern.
2. `create_owner --email` (nucleus, with tests).
3. `neuralops-demo` with the first cloud back-end + the cloud-init template + the DNS step.
4. The reaper + the cloud self-destruct settings + budget alerts.
5. Demo content (if option B) + the demo AI key.
6. A test demo on our own email, end to end, including automatic deletion.

## 2.12 What kind of scripts these are (ruled 2026-10-25)

**Step 1 installer → bash.** It runs on someone else's machine, arriving through `curl … | bash`, before anything is installed; bash is the one thing present on every Linux server. (Docker's, Tailscale's and Ollama's installers are bash for the same reason.)

**Step 2 demo tool → Python.** It runs on OUR machine and does the heavy work: three clouds, DNS records, spending-capped AI keys, end times, retries, reliable clean-up.
- Each cloud's official Python library: `boto3` (AWS), `google-cloud-compute` (Google), `azure-identity` + `azure-mgmt-compute` / `azure-mgmt-network` / `azure-mgmt-resource` (Azure) — real error messages, no parsing of command-line output.
- The team already writes Python (Django / FastAPI) — anyone can maintain it.
- Testable with fake clouds, like the engine suite's fake provider — tests never create real servers.
- Grows into the real "one click": first a command (`neuralops-demo create …`), later the same code behind a button on an admin page next to the demo requests.

**Layout:**
```
neuralops-demo/
├── cli.py                    commands: create · list · extend · delete · reap
├── clouds/
│   ├── base.py               the shared shape: create, public_ip, delete, list
│   ├── aws.py                AWS    (boto3)
│   ├── gcp.py                Google (google-cloud-compute)
│   └── azure.py              Azure  (azure-mgmt-*)
├── dns.py                    creates / removes demo-xxxx.neuralopsnexus.ai
├── ai_keys.py                spending-capped demo AI keys (create / revoke)
├── cloud-init.yaml           the first-boot file (installer + create_owner --email)
└── tests/                    fake clouds — nothing real is created in tests
```
A fourth cloud later (DigitalOcean, Hetzner) = one more file in `clouds/`.

**Rejected:** bash around the cloud command-line tools (fragile, hard to clean up reliably); Terraform / Pulumi (built for permanent infrastructure, awkward for many short-lived servers that must each disappear).

**Where it lives — RULED (owner, 2026-10-25): a separate PRIVATE repo** (`neuralops-demo`). It is our internal operations tool and handles our cloud accounts; the public backend repo keeps only the parts every self-hoster uses (the installer, `create_owner --email`).

## 2.13 Later improvement

**Pre-baked server images** per cloud (built with Packer) with Docker and the NeuralOps images already inside — a demo is then ready in about a minute instead of downloading several GB on first boot.

---

## Decisions open

1. ~~**Tailscale reach (Step 1)**~~ — RULED 2026-10-25: **Funnel** (anyone with the link) by default.
2. **Demo length (Step 2):** 1 hour, or longer for a requested demo.
3. **Demo content:** empty + a ready model (A) or a ready team (B).
4. **Maximum demos at once.**
5. **DNS:** where neuralopsnexus.ai's DNS is managed (Vercel or Cloudflare).
6. **Sending the link:** we email it, or the script sends it.
7. **First cloud:** whichever approves credits first, or a preference.
