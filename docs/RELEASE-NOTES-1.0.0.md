# NeuralOps Nexus 1.0.0

**The first public release.** Self-hosted, multi-tenant AI chat for teams:
your server, your models, your keys. One Docker image carries both servers —
nucleus (the Django API) and nexus-ai (the engine) — plus the realtime
transport; the web app ships separately.

## Highlights

### Smart three-way routing
Every persona can run a model ladder: a cheap **router** answers trivia
inline, hands ordinary work to the persona's **standard** model, and
reserves a **deep bench** (0–N stronger models, ordered) for genuinely hard
problems — the router picks the bench model by each one's strengths note.
A project-wide **default router** fills the seat for any persona without one.
The reply says what happened: "Handed to <model>", and "· fallback" only
when a backup truly answered after a failure.

### Models with real defaults
Register a model and the dialog pre-fills its context window and output cap
from a price catalog the server refreshes daily — and every fresh install
seeds a bundled 322-model snapshot (`manage.py seed_catalog`), so the
numbers are right before the first refresh. Generation settings
(temperature, max output) live on the model card, where they belong. Every
model is checked live before it saves, with the provider's real answer.

### Honest tool use
Tool results are the only ground truth: a persona never invents or
simulates a tool's output. A refused command says "# not executed" with the
reason — never an imagined transcript. Every tool call rides the reply as
an activity trail: what ran, how long, how it went.

### Approvals, questions and nudges
A gated persona proposes a plan before acting; a held tool call shows an
approval card; a persona can ask its caller a question mid-run — the run
parks and resumes in the same bubble when every card is decided (and
expires safely after 24h with nobody answering). Add to a running reply
with a nudge; one that arrives too late posts as a message instead. Only
the person who called the persona can stop, nudge or answer it.

### Chains (runbooks) with a supervisor
An ordered list of persona steps runs as one unit in one chat, each step
building on the last. An optional supervisor persona reviews every stage —
APPROVE / REDO (with notes, bounded) / FAIL — with a pass-unless-broken
bias: style is never a defect. Checkpoint steps park the chain for a
person's answer. Chains cannot run unattended on a schedule if they wait
for people.

### Project memory on pgvector
Documents, chat and tool results embed into a per-project vector index on
the same Postgres (pgvector) — no separate vector database. Retrieval is
always-on but honest: weak matches are discarded, references and scores
show on the reply ("Searched project memory — used N items"), and a memory
pass after tool-heavy replies decides what deserves keeping. Changing a
project's embedder rebuilds its index in the background, atomically.

### The MCP gateway
Your server is itself an MCP server: personal tokens open one JSON-RPC
door (`/api/v1/mcp/`) with tools to list projects and topics, post, ask a
persona and wait, search memory, and list/run/follow chains — always with
exactly the caller's own rights.

### Teams, rights and spend
Role-based rights down to project and topic scope; viewers can read and
post everywhere they can see, and only calling personas is gated. Invites
by email or link; a configure topic only admins see. Per-project monthly
spend limits (estimated prices, block at the cap) and a live spend ticker
per topic. Usage accounting is provider-exact, cache-aware, and every
failed call's input is still billed.

### Deployment
One image, every process picked by command: nucleus API, celery worker +
beat, the engine, the realtime transport. Per-deployment secrets are
generated once (`init-secrets`) — nothing shared is baked in. The release
image carries the application as compiled bytecode; `docker compose` with
the production profile pulls and runs with no source tree. Offline-friendly:
local login, bundled avatars, bundled model catalog.

## Removed in this release
- The Recall pane and the Deliverables pane (and their APIs) left the
  product — project memory above replaced the one, and the other goes
  back to the drawing board.
- The in-app Terminal, server Browser and Web panes: links open in your
  browser; personas' web results show in the chat.

## Upgrading from a pre-1.0 deployment
1.0.0 migrates the database in place (`manage.py migrate` — through
nucleus 0042 + authn 0007; the recall/deliverables tables are dropped,
rows included). Postgres moves to the pgvector image (same major, same
volume); an existing database needs one-time follow-ups: `REINDEX
DATABASE`, then `CREATE DATABASE nexus_vectors` and `CREATE EXTENSION
vector` in it. Pre-1.0 web apps refuse a 1.0.0 server by design — update
both together.

---

*Suites at release: nucleus 464 · engine 117 · web app 1122 — all green.*
