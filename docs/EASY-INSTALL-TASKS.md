# NeuralOps Nexus — Easy Install: developer tasks

**For the developer building this.** Written 2026-10-25. This is the work list: what to build, exactly how it must behave, which files to touch, and how to prove it works. The design and background are in `docs/EASY-INSTALL.md` (read sections 1.1–1.13 and 2.1–2.13 first). Decisions are recorded in `docs/MISSING.md` (Stage 4, "EASY INSTALL").

---

## 0. Before you start

### What already exists (v1, written 2026-10-24)
| File | State |
|---|---|
| `install.sh` (repo root) | Works for the **domain** path. Has a **Cloudflare quick tunnel** path that must be **replaced by Tailscale** (task 1.1). |
| `neuralops/neuralops-cli.sh` | The `neuralops` command. Needs Tailscale awareness and the tunnel parts removed (task 1.1). |
| `docker-compose.neuralops.yaml` | Production profile has the safety fixes (restart policies, Postgres/Redis on localhost, `NGINX_BIND`, `caddy` service). Has a `cloudflared` service that must be **removed** (task 1.1). |

### Rules that apply to every task
1. **Secrets are generated once and never regenerated.** Never overwrite an existing `secrets.env` (it holds the live database password).
2. **Never run `docker compose down -v`.** Data volumes are only ever removed by name, and only after the person types `DELETE`.
3. **Every shell script must pass `shellcheck`** with no warnings (`shellcheck install.sh neuralops/neuralops-cli.sh`) and `bash -n`.
4. **Downloads go to a `.tmp` file first**, then get renamed, so a failed download never leaves a broken file.
5. **Messages are for non-technical people:** one line per step (`✔` done, `!` warning, `✘` stopped + the reason + what to do). Keep the existing helpers (`say`, `ok`, `warn`, `die`, `step`, `ask`, `confirm`).
6. **Questions read from `/dev/tty`** (the script arrives through `curl | bash`). `NEURALOPS_YES=1` means "never ask, take defaults".
7. **Wording:** "source-available", never "open source".
8. The owner verifies every task with the exact commands listed under its **Proof** heading before it counts as done.

### How to test without publishing anything
The installer normally fetches files from GitHub. To test from a local checkout of the branch:
```
NEURALOPS_RAW=file:///path/to/your/clone bash install.sh
```
Use a **fresh machine or VM** (Ubuntu 24.04, 4 GB+ memory). Running it on a machine that already has a NeuralOps dev stack mixes the two.

---

# STEP 1 — the one-command installer

## Task 1.1 — Replace the Cloudflare quick tunnel with Tailscale

**Why:** a machine at home or in an office can't be reached from the internet. Tailscale gives it a permanent HTTPS address (`https://<machine>.<tailnet>.ts.net`). The quick tunnel's address changed on every restart, which made it unusable for real teams.

**Decision (owner, 2026-10-25): Tailscale Funnel by default.** Anyone with the link can open the server; teammates install nothing. `serve` (only the person's own Tailscale devices) stays available as a setting.

### 1.1.a The question (install.sh, `choose_access`)
Replace the current two choices with exactly this text:
```
How will you reach NeuralOps?
  1) Tailscale (recommended for a machine at home or in the office)
     a permanent secure address; needs a free Tailscale account
  2) I have a domain (for a cloud server with a public address)
     automatic HTTPS certificate
```
- Default answer: **1**.
- `NEURALOPS_MODE` values become `tailscale` | `domain` (remove `tunnel`). Any other value → `die "NEURALOPS_MODE must be 'tailscale' or 'domain'."`
- Compose profiles: `tailscale` → `production`; `domain` → `production,https` (unchanged).
- New settings (document them in the script's header comment):
  - `NEURALOPS_TS_REACH` — `funnel` (default) or `serve`.
  - `NEURALOPS_TS_AUTHKEY` — optional Tailscale auth key for unattended installs (no login link).
  - `NEURALOPS_TS_HOSTNAME` — optional, default `neuralops`.

### 1.1.b A new function in install.sh: Tailscale setup
Runs **after** the files are prepared and **before** NeuralOps starts, because the server's address must be written into `app.env` before the app starts.

Behaviour, in order:

1. **Install Tailscale if missing.**
   - Check `command -v tailscale`.
   - If missing: say *"Installing Tailscale (official script from tailscale.com)"* and run `curl -fsSL https://tailscale.com/install.sh | sh` (with sudo when not root). On failure: `die "Tailscale installation failed."`
   - Make sure the service runs: `systemctl enable --now tailscaled` (ignore errors on systems without systemd).
   - Tailscale runs **on the machine itself**, not in a container: it starts at boot by itself and its address never changes.

2. **Connect the machine to the person's Tailscale account** (skip if already connected).
   - "Connected" means `tailscale status --json` reports `"BackendState": "Running"`. Read the JSON with `grep`/`sed` (don't require `jq`; it isn't installed everywhere).
   - **With `NEURALOPS_TS_AUTHKEY`:** run `tailscale up --authkey=<key> --hostname=<hostname>`. Failure → `die` with Tailscale's error.
   - **Without it (interactive):**
     - Start `tailscale up --hostname=<hostname>` **in the background** (it blocks until the person signs in).
     - Poll `tailscale status --json` every 2 seconds for the `"AuthURL"` field.
     - When it appears, show it in a clear box:
       ```
       ┌──────────────────────────────────────────────────────────────┐
       │  Sign in to Tailscale to connect this machine:               │
       │  https://login.tailscale.com/a/xxxxxxxx                      │
       │  Open it on your phone or laptop. No account yet? It's free. │
       └──────────────────────────────────────────────────────────────┘
       ```
     - Keep polling until `BackendState` is `Running`. Print a dot every few seconds so the person sees it's waiting.
     - Time limit **10 minutes**. On timeout: `die "Waiting for the Tailscale sign-in timed out. Run the installer again; it will continue where it stopped."` (task 1.2 makes that true).
   - With `NEURALOPS_YES=1` and no auth key, still show the link and wait (an unattended install without a key cannot sign in by itself; the message must say so).

3. **Publish NeuralOps through Tailscale.**
   - `funnel` (default): `tailscale funnel --bg 8095` → `https://<machine>.<tailnet>.ts.net` forwards to nginx at `127.0.0.1:8095`.
   - `serve`: `tailscale serve --bg 8095` (only the person's own Tailscale devices can open it).
   - **First Funnel on an account:** Tailscale asks the account owner to allow Funnel (and HTTPS certificates). The command prints a link like `https://login.tailscale.com/f/funnel?node=...` and waits. Handle it the same way as the sign-in: run it in the background, capture its output, show that link in the same kind of box (*"Allow this machine to be reached with a link: …"*), and wait until `tailscale funnel status` shows Funnel on (time limit 10 minutes, same timeout message).
   - Must be safe to run again: if the funnel/serve for port 8095 is already set, don't fail.

4. **Read the address.**
   - From `tailscale status --json`: the `"DNSName"` of `Self` (it's the first `DNSName` in the output; `Self` comes before `Peer`). Remove the trailing dot. Address = `https://<that name>`.
   - If no name is found: `die "Tailscale is connected but has no name for this machine. Check MagicDNS is on in the Tailscale admin page, then run the installer again."`
   - Write it into `app.env` (both `NEURALOPS_SERVER_URL` and `CENTRIFUGO_ALLOWED_ORIGINS`), using the existing `write_app_env`.
   - Print `✔ Address: https://...`.

### 1.1.c Remove the tunnel everywhere
| File | Remove |
|---|---|
| `install.sh` | `start_tunnel_first`, the `tunnel` branch in `choose_access`, the systemd unit `neuralops-address.service` written in `install_helper`, the tunnel warning in `finish`, every mention of Cloudflare / trycloudflare in comments |
| `neuralops/neuralops-cli.sh` | the tunnel branch in `cmd_address`, the tunnel step in `start`, the `/etc/systemd/system/neuralops-address.service` removal in `uninstall` |
| `docker-compose.neuralops.yaml` | the whole `cloudflared` service and its comment block. Update the comment above `caddy`, which mentions "exactly one of these two": there is now only one (Caddy, for domains; Tailscale runs on the machine, not in compose) |

### 1.1.d The `neuralops` command learns Tailscale (neuralops-cli.sh)
- **`neuralops address`:**
  - `domain` mode: print the address from `app.env` (as now).
  - `tailscale` mode: read the current name from `tailscale status --json` (same method as 1.1.b step 4). If it differs from `app.env` (for example the machine was renamed in Tailscale), rewrite `app.env` and recreate only `nucleus` and `centrifugo` (`compose up -d --force-recreate --no-deps nucleus centrifugo`), then warn *"The address changed. Update it in the app."* If Tailscale is not connected: `die "Tailscale is not connected on this machine. Run: sudo tailscale up"`.
- **`neuralops status`:** also print one line for Tailscale in `tailscale` mode: connected or not, and Funnel on/off.
- **`neuralops uninstall`** (only when the person typed `DELETE`, `tailscale` mode only): run `tailscale serve reset` (clears this machine's serve/funnel settings). Leave Tailscale itself installed and connected, and print: *"Tailscale is still installed. To disconnect this machine from your Tailscale account: sudo tailscale logout"*.

### 1.1.e The final box (install.sh `finish`)
Same box as now. Show the Tailscale address. Remove the tunnel warning. In `tailscale` mode add one line: *"Anyone with this address can open the sign-in page; only people you invite can get in."*

### Proof (owner)
- On a **fresh local Linux machine or VM**: run the installer, choose 1, sign in with the link, allow Funnel with the second link. It finishes with a `https://….ts.net` address. In the hosted app (neuralopsnexus.ai): add the server, claim it, create a project, and get a persona reply.
- Open the same address from a phone that is **not** on Tailscale: the app can reach it (Funnel works).
- Reboot the machine: NeuralOps and the address come back by themselves; `neuralops address` prints the same address.
- `shellcheck` clean on both scripts.

---

## Task 1.2 — Resume a half-finished install

**Why:** if the installer stops part-way (a timeout, a lost connection, Ctrl+C), running it again must finish the job. Today it sees `secrets.env` and refuses ("already installed") even though nothing works.

### Behaviour
1. **The "finished" marker:** the very last thing the installer does, after `install_helper` and before the final box, is write `$NEURALOPS_DIR/neuralops/.installed` (the current date inside is enough).
2. **`check_existing` decides between three situations:**

| Found | Meaning | What the installer does |
|---|---|---|
| `.installed` exists | A complete install | Prints *"NeuralOps is already installed. To upgrade: neuralops update · To see its address: neuralops address"* and stops (exit 0). |
| `secrets.env` exists, no `.installed` | A previous attempt stopped half-way | Warns *"A previous install stopped part-way. Continuing it (your secrets are kept)."* and continues in **resume mode** |
| neither | A fresh machine | Normal install |

3. **Resume mode:**
   - Re-use the earlier choice: read `NEURALOPS_MODE` from `neuralops/install.conf` and `NEURALOPS_DOMAIN` from `neuralops/infra.env`, so the person isn't asked again and can't accidentally switch paths. If those files are missing, ask as usual.
   - **Never** generate secrets again; skip the "old database without secrets" safety check (the secrets exist).
   - Everything else runs again as normal. Every step is already safe to repeat (folders, file downloads, Tailscale setup, `compose up`, vector DB, migrate, seeds).
4. **Machines installed with v1** (they have `secrets.env` but no `.installed`): `neuralops update` should write `.installed` if it's missing, so those machines are treated as complete from then on.

### Proof (owner)
- Start a fresh install, and press Ctrl+C right after the line *"Generated this install's own secrets"*. Run the installer again: it says it's continuing, doesn't ask the question again, and finishes. The database works (no password error).
- Run it a third time: it says "already installed" and stops.

---

## Task 1.3 — The short address `get.neuralopsnexus.ai`

**Who:** the owner (Vercel access) together with the developer.

1. In Vercel, add the domain `get.neuralopsnexus.ai` to a project (a new tiny project, or the existing one, with a rule that applies only to that host).
2. Add a redirect from `/` to `https://raw.githubusercontent.com/mapax-io/neuralops-nexus/main/install.sh` (temporary redirect, not permanent, so the target can change later). Example `vercel.json` for a tiny dedicated project:
   ```json
   { "redirects": [ { "source": "/", "destination": "https://raw.githubusercontent.com/mapax-io/neuralops-nexus/main/install.sh", "permanent": false } ] }
   ```
3. Add the DNS record Vercel asks for (`get` → Vercel).

**Note:** the address only works once `install.sh` is on the `main` branch of `mapax-io/neuralops-nexus` (after the release merge).

### Proof
`curl -fsSL https://get.neuralopsnexus.ai | head -3` prints the first lines of `install.sh`.

---

## Task 1.4 — Documentation for users

1. **readme.md, section "1. Self-hosting NeuralOps":** put the one command at the top as the main way to install, with the two choices explained in two lines and the "careful users" variant (download → read → run). Keep the existing manual steps below it, under "Manual install (advanced)".
2. **docs/EASY-INSTALL.md:** update the status markers (TO BUILD → BUILT) for what you finished, and remove the Cloudflare mentions.
3. **docs/MISSING.md:** stamp Phase 1 as BUILT, with the proof results.

---

## Task 1.5 — Proof runs (owner, after 1.1–1.4)

| # | Machine | Path | Must pass |
|---|---|---|---|
| P1 | Fresh local Linux machine / VM | Tailscale | install finishes · hosted app connects · claim · project · persona replies |
| P2 | Fresh cloud VPS with a domain pointed at it | Domain | same, and the HTTPS certificate is valid |
| P3 | Either | — | run the installer again → "already installed" |
| P4 | Either | — | reboot → NeuralOps back by itself, same address |
| P5 | Either | — | `neuralops backup` → 3 files · `neuralops update` → still works, data kept |
| P6 | Either | — | `neuralops uninstall` keeping data → `neuralops start` brings it back |
| P7 | Fresh machine | Either | Ctrl+C mid-install → run again → finishes (task 1.2) |

---

# STEP 2 — one-click demo servers

**Not started until the cloud credits are approved** (Microsoft for Startups, Google for Startups or AWS Activate). Task 2.1 can be built earlier, because it lives in the public backend and is useful on its own.

## Task 2.1 — `create_owner --email` (public backend, nucleus)

**Why:** for a demo server, **we** set it up, but the person who requested the demo must become its owner. Today `create_owner` only works when that person types a code at the portal themselves.

**Where:** `modules/nexus-nucleus/authn/management/commands/create_owner.py` (the command), `authn/services.py` (`claim_install`, `server_needs_owner`), and the API endpoint where a signed-in person's portal (Supabase) token is exchanged for access to this server (in `authn/api.py`).

### Behaviour
1. `manage.py create_owner --email person@company.com`:
   - If the server already has an owner → refuse (same message as today).
   - Otherwise **store a reservation**: "this server's first owner must be person@company.com". Store it in the database (your choice of a small model or a settings row; it needs a migration either way). Lowercase the email.
   - Print: *"This server is reserved for person@company.com. They become its owner the first time they sign in with that email."*
   - Must work without a keyboard (it runs inside the demo server's first-boot script): never call `input()` in this mode; use the default workspace name.
2. **When someone signs in to this server while it has no owner and a reservation exists:**
   - The portal token's email matches the reservation (case-insensitive) **and** the token says the email is verified → run the existing `claim_install` (one creation path; don't write a second one), with the default workspace name. Then delete the reservation. The person carries on, signed in, as the owner.
   - The email doesn't match, or isn't verified → refuse with a clear message: *"This server is reserved for its demo owner."* Nothing is created.
3. While a reservation exists, the normal code-flow claim (`create_owner` without `--email`) refuses with *"This server is reserved for <email>."*
4. `create_owner --email` run again with a different email while no owner exists → replaces the reservation (we may correct a typo).

### Tests (nucleus suite; the owner runs the full suite before and after)
- the reserved email, verified → becomes owner; reservation gone
- a different email → refused, no owner created
- the right email but unverified → refused
- a second sign-in after the claim → normal sign-in, not a second claim
- `--email` when an owner exists → refused
- the code-flow claim while a reservation exists → refused
- `--email` twice → the second reservation wins

### Proof (owner)
The full nucleus suite is green at its new count; then on a test server: `create_owner --email <your email>` → sign in from the hosted app with that email → you're the owner; with another account → refused.

## Task 2.2 — The `neuralops-demo` tool (new PRIVATE repo)

**Ruled:** Python, in a **separate private repo** named `neuralops-demo`. It runs on our machine (node3 or a small always-on box).

### Layout
```
neuralops-demo/
├── cli.py              commands: create · list · extend · delete · reap
├── config.py           reads settings (below); no secrets in code
├── clouds/
│   ├── base.py         the interface every cloud implements
│   ├── aws.py          boto3
│   ├── gcp.py          google-cloud-compute
│   └── azure.py        azure-identity + azure-mgmt-compute / -network / -resource
├── dns.py              create/delete demo-xxxx.neuralopsnexus.ai
├── ai_keys.py          create/revoke a spending-capped AI key per demo
├── cloud-init.yaml.j2  the first-boot file (template)
├── tests/              with fake clouds, fake DNS, fake key provider
└── README.md           how to set up credentials and run it
```

### Settings (environment variables or a config file outside the repo)
Cloud credentials use each cloud's standard method (AWS profile, Google application-default credentials, Azure service principal), always for a **demo-only** account/project/subscription. Also: the DNS provider token, the AI key provisioning key, the maximum number of demos at once, the default demo length, the default cloud, and region/size per cloud.

### The interface (clouds/base.py)
Every cloud implements the same four operations:
- `create(demo_id, user_data, expires_at, size) → server_ref`
- `public_ip(server_ref) → str` (waits until the IP exists)
- `delete(server_ref)` (must be safe to call twice)
- `list_demos() → [ {demo_id, server_ref, expires_at, email, ip} ]`, found by **tag/label `neuralops-demo`**

**The cloud's tags are the source of truth** (id, end time, email). A local file may cache them for speed, but `list` and `reap` always ask the clouds.

### Commands
| Command | Behaviour |
|---|---|
| `create --cloud aws\|gcp\|azure --email E [--hours N]` | The flow below |
| `list` | Every running demo on every configured cloud: id, cloud, email, address, time left |
| `extend <id> --hours N` | Moves the end time (updates the tag, and the cloud's own timer where possible) |
| `delete <id>` | Deletes server + DNS record + AI key. Safe if any part is already gone |
| `reap` | Deletes every demo past its end time on every cloud. Run by a timer (task 2.6) |

### The `create` flow
1. Make an id: `d-` + 4 random lowercase letters/digits (e.g. `d-x7k2`). Address: `demo-x7k2.neuralopsnexus.ai`. End time: now + N hours (UTC).
2. Refuse if the number of running demos has reached the maximum.
3. Create the demo AI key (task 2.4) with its spending limit (if demos come with a model; decision open).
4. Render `cloud-init.yaml.j2` (task 2.5) with: the address, the requester's email, the AI key, and the end time in minutes.
5. `create` on the chosen cloud with tags `neuralops-demo=<id>`, `expires=<end time>`, `owner-email=<email>`.
6. `public_ip` → create the DNS `A` record (task 2.3).
7. Wait until `https://<address>/api/v1/projects/` answers **401** (installed, certificate issued, app alive). Show progress. Time limit around 20 minutes; on timeout, print the cloud's console output if available and keep the server for inspection (don't delete it automatically on this path).
8. Print the link and a ready-to-send message for the requester.
9. **If any step fails before the server is ready:** clean up what was created (AI key, DNS record, server) and say exactly what failed.

## Task 2.3 — DNS (dns.py)
- Create/delete an `A` record `demo-<id>.neuralopsnexus.ai → <ip>`, short TTL (60 s).
- Provider: wherever neuralopsnexus.ai's DNS is managed (**decision open: Vercel DNS or Cloudflare**; both have an API). Write the module against one provider, behind two functions (`add_record`, `remove_record`), so switching later touches only this file.

## Task 2.4 — Demo AI keys (ai_keys.py)
- Create one key per demo with a **hard spending limit** (e.g. OpenRouter's key provisioning API, which supports a credit limit per key), named after the demo id.
- Revoke it on `delete` / `reap`.
- The key travels only inside the first-boot file and is stored only on the demo server.

## Task 2.5 — The first-boot file (cloud-init.yaml.j2)
Runs as root on the new server, with no SSH involved:
1. Install NeuralOps unattended:
   `curl -fsSL https://get.neuralopsnexus.ai | NEURALOPS_YES=1 NEURALOPS_MODE=domain NEURALOPS_DOMAIN=<address> bash`
2. Reserve ownership (task 2.1):
   `docker exec -w /nexus/nucleus -e PYTHONPATH=/nexus/nucleus neuralops-nucleus /opt/venv/nucleus-env/bin/python manage.py create_owner --email <email>`
3. Demo content and the demo model, if decided (a `seed_demo` command in the public backend would be a separate small task).
4. Backstop: `shutdown -h +<minutes until end>`.

## Task 2.6 — Never forget a server (three layers)
1. **The reaper:** `neuralops-demo reap` every 5 minutes (a systemd timer or cron on our machine). Log what it deletes.
2. **The cloud's own self-destruct where it exists:**
   - **AWS:** create instances with `InstanceInitiatedShutdownBehavior=terminate`. With the backstop shutdown in cloud-init, AWS deletes the server at the end even if our reaper is down.
   - **Google:** create instances with a maximum run duration of N hours and termination action `DELETE`.
   - **Azure:** no built-in option. Put each demo in **its own resource group** so one delete removes everything (server, disk, IP, network). The reaper deletes the group.
3. **Budget alerts** on each cloud's demo account (owner sets these up in each cloud's console).

## Task 2.7 — Cloud specifics (in each cloud file)
Size: **the 4 GB memory class, 30 GB disk, Ubuntu 24.04 (x86_64), firewall 80 + 443 only, no SSH from the internet.**
- **AWS:** `t3.medium`; Ubuntu image ID from AWS's public SSM parameter for Ubuntu 24.04 (don't hard-code an AMI ID); a security group with 80/443 only (create once, reuse); tags on the instance.
- **Google:** `e2-medium`; image family `ubuntu-2404-lts-amd64` from project `ubuntu-os-cloud`; a firewall rule for a network tag (create once, reuse); labels on the instance; user data passed as the `user-data` metadata key.
- **Azure:** `Standard_B2s`; image `Ubuntu2404`; one resource group per demo, tagged; open ports 80/443 on the VM's network security group; user data passed as custom data.
- Check the size and image names against each cloud at build time; clouds rename them.

## Task 2.8 — Tests and the end-to-end proof
- **Unit tests with fakes** for: the create flow (including cleanup when a step fails), `list`, `extend`, `delete` (safe twice), `reap` (deletes only expired demos), the maximum-demos refusal, and the template rendering. Tests must never create real cloud resources.
- **End-to-end proof (owner):** on the first approved cloud, `create --email <owner's email> --hours 1` → link works → sign in → owner → a persona replies → `delete` → server, DNS record and key are all gone (check in the cloud console). Then create one more with `--hours 1`, stop the reaper timer, and confirm the cloud's own self-destruct (AWS/Google) removes it at the end.

---

## Decisions still open (ask the owner; don't guess)
1. **Demo length:** 1 hour, or longer for a requested demo.
2. **Demo content:** an empty workspace plus a ready AI model, or a ready-made team (sample personas and a chain).
3. **Maximum demos running at once.**
4. **DNS provider** for neuralopsnexus.ai (Vercel or Cloudflare).
5. **Sending the link:** printed for us to email, or sent by the tool.
6. **First cloud:** whichever approves credits first, or a preference.

## Already decided (don't reopen)
- Installer = bash; demo tool = Python, in a separate private repo.
- Tailscale = **Funnel** by default (anyone with the link); `serve` available as a setting.
- Cloudflare quick tunnel: removed.
- One VM per demo, each deleted automatically at the end.
- Linux x86_64 only for the installer, for now.
