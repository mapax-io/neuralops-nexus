# NeuralOps — Stage 3: the GitHub launch + the release image

**STANDING RULE (owner, 2026-10-22 22:59: "why, when things are not yet
finalized"):** Claude hands over NO docker build/push, NO PR-merge and NO
tag commands until the owner says FINALIZE (or LAUNCH). Until then the only
commands that flow are the normal dev loop: suites, commits, branch pushes.
The launch checklist at the bottom of this file is PARKED and runs only on
that word. **FINALIZE said 2026-10-22 23:15.** State since: Docker Hub
1.0.0 + latest REBUILT and RE-PUSHED with everything in them (new digest
d18e3f77…, replacing the hardening-less 3d0ff42…); readme launch pass
committed (e756103). Owner's merge flow (his ruling 23:27): merge
step8-switchover → main here, then merge to the main (mapax-io)
repository — so the readme's mapax-io clone/contributing links stay.
Still open: owner's Supabase chores + smoke-stack down + live walkthrough,
then the merges, then the tag move + release page (checklist steps 3+5).

**Drafted 2026-10-22 (owner's plan: "i have to launch it on Github and we
also need to create both servers (ai and nucleus) into api image then in
docker").** Code state: backend f5a5d97 (step8-switchover, unpushed with
c62663f), frontend d40dfeb. Suites: nucleus 464 · engine 117 · frontend 1122.

**DECIDED (owner, 2026-10-22 22:05):** version **1.0.0**; GitHub lands via
**PR to main**; keys **rotated and the gateway token revoked**; image code
via **Nuitka** — BUT (owner, 22:15) the image build itself is the LAST step,
done only at launch time; the Nuitka-vs-bytecode call is made then (Claude
flagged the cost — see B1; bytecode is the agreed escape hatch if Nuitka
fights Django/torch). Nothing is built or compiled yet.

**COMMITTED (owner, 2026-10-22 22:25): backend 89a89bb, frontend bb5c882.**
requirements.lock regenerated and VERIFIED (pydantic-ai-slim 2.55.0 + the
web-fetch deps — beautifulsoup4/markdownify/lxml/ddgs — all present;
torch 2.14.1+cpu; pytest baked). B2 is DONE. Release notes drafted:
docs/RELEASE-NOTES-1.0.0.md. Unpushed backend commits now: c62663f,
f5a5d97, 89a89bb.

**BUILT so far (2026-10-22 evening):** version bumped to 1.0.0 in all three
places (neuralops/Dockerfile NEURALOPS_VERSION, infra.env.example
NEURALOPS_IMAGE, web app version.ts APP_VERSION + COMPATIBLE_SERVER_VERSION
+ its test); docker-compose.neuralops.yaml PRODUCTION profile caught up to
Step 8 (real engine command fastapi_app.main, NEXUS_VECTOR_DB_URL, no host
port, postgres → pgvector/pgvector:0.8.7-pg17, chromadb service removed).

---

## A. What already exists (read before changing anything)

- **One unified image** (`neuralops/Dockerfile`, context = repo root):
  nucleus venv (py3.13) + rebuilt-engine venv (py3.13) + centrifugo binary
  + filesystem/git MCPs + `init-secrets`. Entry: `entrypoint.sh <mode>`.
- **The image carries NO app code** — the dev profile bind-mounts
  modules/nexus-nucleus → /nexus/nucleus and modules/nexus-ai → /nexus/ai.
  The old plan said "distribution code via Nuitka, decided later".
- **docker-compose.neuralops.yaml**: dev profile is CURRENT (rebuilt engine,
  pgvector postgres, no chromadb). Production profile is STALE pre-Step-8:
  legacy engine command (`apps.main:app`, currently `tail -f /dev/null`),
  chromadb service + CHROMA_* env, `postgres:17-alpine` (no pgvector),
  published engine port 8020, no NEXUS_VECTOR_DB_URL.
- Baked-in, safe-by-design: SUPABASE_URL/ANON_KEY (shared project, RLS),
  PORTAL_URL, NEURALOPS_VERSION=0.8.0. Per-deployment secrets come from
  `init-secrets` → neuralops/secrets.env (append-only — NEVER regenerate an
  existing deployment's file).

## B. The release image (the "both servers into one API image" half)

1. **Bake the source code into the final stage** — plain `COPY`, no Nuitka:
   the repo launches PUBLIC on GitHub, so compiling/obfuscating the same
   code that anyone can clone buys nothing and costs build complexity.
   `COPY modules/nexus-nucleus /nexus/nucleus` and
   `COPY modules/nexus-ai /nexus/ai` (after the venv copies, chowned to
   nexus). The DEV profile keeps working unchanged: its bind mounts simply
   shadow the baked code. One Dockerfile serves both.
   **[OWNER DECIDES — recommended: plain COPY]**
2. **requirements.lock regeneration FIRST** (7c, already queued): the dev
   container had `pydantic-ai-slim[web-fetch]` installed by hand — if the
   lock doesn't carry it, the release image loses web_fetch silently.
   Regenerate inside the dev engine container:
   `pip freeze > requirements.lock` (owner runs, Claude checks the diff).
3. **.dockerignore check**: docs/, logs (*.log, test-output.txt), projects/,
   neuralops/*.env + secrets backups, .git — none of it may enter the build
   context's COPY. (`data/` at repo root too.)
4. **Version bump**: NEURALOPS_VERSION + frontend
   `src/lib/version.ts` COMPATIBLE_SERVER_VERSION + infra.env.example's
   NEURALOPS_IMAGE tag, all in one change.
   **[OWNER DECIDES the number — recommended: 0.9.0]**
5. **Build + smoke — DONE 2026-10-22 22:41.** Image built in 244s
   (bytecode compile + venv import checks pass at build time). Production
   profile smoke on the fresh image: fresh postgres volume, CREATE DATABASE
   nexus_vectors + extension, migrate from the BAKED code through nucleus
   0042 + authn 0007, seed_catalog OK ("Seeded 267…322 in the file" — beat
   fired the daily refresh at startup and raced 55 rows in; both roads are
   never-downgrade, harmless), nginx→nucleus answers, engine uvicorn up on
   fastapi_app.main. Three gotchas found + fixed on the way, each a
   REAL-INSTALL lesson for the readme:
   - the deployment's infra.env still pinned the old image tag (0.1.2) —
     fixed to 1.0.0; keep NEURALOPS_IMAGE in sync at every bump;
   - a pre-existing production postgres VOLUME carries its old password —
     a stale smoke volume is removed (never `down -v`: that would take the
     dev volumes too);
   - a secrets.env from before Step 4 has no SECRET_KEY — production
     refuses to boot (by design); APPEND one line, never regenerate the
     file. Fresh installs get it from init-secrets automatically.
   (Baked-bytecode tracebacks print /code/nucleus/… paths — cosmetic.)
   In-image suites: not applicable by design — tests are stripped from the
   distribution image; the suites run in the dev profile, and the smoke
   above is the image's own proof.

## C. docker-compose.neuralops.yaml — production profile catch-up

- `postgres` → `pgvector/pgvector:0.8.7-pg17` (same major; first boot of an
  EXISTING deployment needs the same one-time follow-ups dev did: REINDEX
  DATABASE + `CREATE DATABASE nexus_vectors` + `CREATE EXTENSION vector`).
  A fresh deployment needs nexus_vectors created once — document in readme.
- `nexus-ai`: real command
  (`nexus-ai-env python3 -m uvicorn fastapi_app.main:app --host 0.0.0.0
  --port 8000`), env → `NEXUS_NUCLEUS_URL=http://nucleus:8000` +
  `NEXUS_VECTOR_DB_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/nexus_vectors`,
  drop CHROMA_*/EMBEDDING_* legacy vars, drop the published host port
  (dev's ruling: the engine takes no outside requests; internal key is the
  second lock), keep the fastembed cache + projects mounts.
- Delete the `chromadb` service + volume from the production profile.
- First-run migrate: document the standard setup sequence in the readme —
  `migrate` → `seed_permissions`/provisioning as nucleus already does →
  `seed_catalog` (the bundled 322-row snapshot ships in the image now).

## D. The GitHub launch

1. **Pre-push security sweep — DONE 2026-10-22 22:20.** Findings: the
   tracked `neuralops/secrets.env.back*` files and the frontend scratch
   files. OWNER'S RULING: "those are fake and mostly deleted" — no history
   scrub needed. Gitignore holes closed anyway (neuralops/secrets.env*,
   test-output.txt, the four frontend scratch names); the untrack commands
   were handed over and ride the next commit.
2. **Rotations — CONFIRMED by owner 2026-10-22 22:05** (OpenAI + Anthropic
   keys rotated, the pasted gateway token revoked).
3. **Branch**: merge `step8-switchover` → `main` (fast-forward or merge
   commit — owner's habit), push main + tag `v<version>`.
   **[OWNER DECIDES: merge to main, or push the branch and merge on GitHub
   via PR — recommended: PR, it gives the launch a reviewable record]**
4. **Docker Hub**: push `noamanfaisal/neuralops:<version>` + `:latest`.
5. **Release notes**: Claude drafts from the docs (NUCLEUS-REVAMP /
   FRONTEND-REVAMP BUILT blocks since 0.8.0).
6. **Frontend repo**: push `noamanfaisal` branch (d40dfeb already local);
   same merge question as the backend.

## E. Remaining Stage 3 chores (from MISSING)

- Supabase: remove the legacy device-verify function; delete the
  test-install-1 phone_home_events row.
- Fresh `seed_catalog --regenerate` + commit as the release snapshot
  (the 2026-10-22 322-row file is current enough unless days pass).

Order of work (owner's ruling 2026-10-22 22:15 — the image build is LAST):
D1 security sweep (owner ruled the findings fake) → B2 (requirements.lock,
DONE) → E (Supabase chores, any time) → then AT FINALIZE: the checklist
below. B4 (version bump), C (compose), B1/B3/B5 (image, smoke) already done.

## PARKED LAUNCH CHECKLIST — runs ONLY when the owner says FINALIZE

1. DONE — suites green at the final targets (nucleus 464 · engine 118 ·
   frontend 1122); everything committed and the branches pushed.
2. On GitHub, open + merge the two PRs:
   neuralops-nexus-backend `step8-switchover → main`,
   neuralops-nexus-web-app `noamanfaisal → main`.
3. Move the tag onto the REAL merged main (it currently marks the old one):
   `git fetch origin && git tag -f v1.0.0 origin/main && git push -f origin v1.0.0`.
4. DONE 2026-10-22 23:15 (digest d18e3f77…) — rebuild + re-push the image
   so the public 1.0.0 carries everything:
   `docker build -f neuralops/Dockerfile -t noamanfaisal/neuralops:1.0.0 .`
   then tag `:latest`, `docker push` both.
5. GitHub release for v1.0.0 with docs/RELEASE-NOTES-1.0.0.md as its text.
