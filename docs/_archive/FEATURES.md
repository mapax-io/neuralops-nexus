# Feature List

A working inventory of what Nexus does today, what's actively being hardened, and what's open for someone to pick up. Items in "Proposed" are written issue-sized on purpose — if one looks like something you want to build, open it on the [Project board](https://github.com/orgs/NeuralOPS-Nexus/projects/3) (or comment on the matching issue if it's already there) before starting, per [`how-to-contribute.md`](./how-to-contribute.md).

## Shipped

**Workspace structure** — Company → Project → Channel → Topic. A Project is a team or initiative; a Channel groups related conversations; a Topic is the actual thread AI responds in.

**Humans and personas as equal members** — one underlying `User` model covers both. A persona can be `@mention`ed, appear in a member list, and be added to a project through the same invite flow as a human, because it *is* one, identity-wise.

**Directives** — shape a persona's output with `@chart`, `@table`, `@diagram`, `@form`, `@code`, `@terminal`, or `@html` instead of getting plain text back.

**Sessions** — `@PersonaName @session` opens a 30-minute window where plain messages route to that persona automatically, without re-mentioning it every time. `@session close` / `@session end` ends it early.

**Tool-connected agents via MCP** — an Agent pairs one AI Model with one MCP Server, so a persona built on it can call real tools, not just generate text. Adding a new tool is standing up an MCP server and registering its URL — no Nexus code changes required.

**Proven integrations** — project filesystem and monday.com, demoed end-to-end. Jira works at the API level. Three example MCP servers ship in `mcps/`: SerpAPI shopping search, Odoo ERP, filesystem.

**Single-image self-hosting** — one Docker image (`noamanfaisal/neuralops`) launched in different modes across nine containers, ~4GB RAM, exposed via Tailscale Funnel or your own reverse proxy. See [`SELF-HOST.md`](./SELF-HOST.md).

**No-email invite flow** — invite a teammate from inside a chat, get a link back, send it however you already talk to them. No SMTP server required for a self-hosted deployment to work.

**RBAC with custom roles** — Owner/Admin/Member/Viewer seeded by default at company, project, and topic scope, but not fixed — a company can define its own roles (e.g. a narrow "Persona Builder" role that can only create/edit/delete personas) and stack them alongside the defaults.

**Avatars and presence** — auto-assigned avatars for both humans and personas, typing/thinking status indicators so you can see when a persona is actually working on a response.

**Scheduled persona queries** — a persona can be asked to run on a schedule inside a topic, not just in response to a message.

## In progress

**Team & permission consistency** — closing the gap between every membership path (invite, acceptance, topic-scoped invites) and full RBAC enforcement. See the roadmap's "Now" section — this is the current top priority.

**Self-host hardening** — smoothing out the single-image deploy across more reverse-proxy setups and host environments, with clearer failures when something's misconfigured.

**Scheduled persona queries, end-to-end validation** — the feature above is shipped, but hasn't had a dedicated test pass of its own yet; queued up next.

**Persona chaining ("swarm mode").** A persona can be authorized to hand a task off to another persona mid-response — `authorized_handoffs` is a new self-referential, non-symmetrical many-to-many on `Persona` (set per-persona via `/add-persona` or `/edit-persona`). Triggered with a `/swarm` directive on an @mention; the model gets a `handoff_task` tool it can call with a target persona and instructions, and control passes to that persona (up to 7 hops) with the handoff instructions injected into history as the next turn's context. Known issues from an initial pass, to close out before calling this done: editing a persona's handoffs can only add, never remove one (patch path uses `.add()` instead of `.set()`); the output-type resolver for swarm runs is an unfinished stub, which also has the side effect of skipping the system-prompt block that tells the model about its handoff options; handoff targets aren't validated against the persona's own company/project.

## Proposed — good places to start

**New MCP connectors.** The lowest-friction way to contribute something a real team will use. Slack, GitHub, Notion, Linear, a generic REST/CRM connector, an internal wiki — pick a tool your own team runs on, build an MCP server for it following the pattern in `mcps/`, and it plugs into any persona the same way filesystem and monday.com do today.

**Multi-tool persona support.** Reworking `AIAgent`'s single-MCP-server relationship into something that supports more than one tool per persona. Bigger scope — worth discussing shape on the Project board before diving in, since it touches the Agent/MCPServer data model directly.

**OAuth for MCP server connections.** Token-refresh and consent flow for tools that need OAuth instead of a static API token.

**Project-scoped persona and model permissions.** Extending the project-scope treatment Agents and MCP Servers already have to Personas and AI Models, which are currently company-scope-only for creation.

**A basic load-testing harness.** Even a simple script that spins up N concurrent users across M topics and reports where Celery/Centrifugo start to strain would be a real contribution — nothing like this exists yet.

**Additional output directives, or directive composability.** New `@directive` types beyond the current seven, or ways for one directive's output to feed another (a `@form` submission populating a `@chart`, for instance).

**Documentation.** More self-host walkthroughs for specific environments (bare VPS, Unraid, a specific cloud provider), a clearer first-time-contributor path through the codebase, diagrams of how nucleus/nexus-ai/centrifugo talk to each other. Documentation contributions are reviewed the same way code is — see `how-to-contribute.md`.

**A "configure topic" for admin-driven setup.** A dedicated topic (not a whole channel) where a Project Owner or Project Admin gives plain-language instructions, and the system uses its own (internal, first-party) MCP server to actually create/edit Agents, Personas, and Models on their behalf — configuration via conversation instead of forms. *(Open questions: is this a new internal MCP server distinct from the existing three examples, is it permission-gated to Owner/Admin only at the call site or also enforced by the internal MCP itself, and does every change it makes need an audit-log entry given it's mutating config, not just chatting.)*

**Unique names for Models, Personas, and Agents.** Enforce name uniqueness so `@mention`s and tool/model pickers aren't ambiguous. *(Open question: scoped per-company, or per-project — Models and Personas are currently company-scope-only for creation per the roadmap's "Next" section, so company-wide uniqueness may be the natural fit, but worth confirming rather than assuming.)*
