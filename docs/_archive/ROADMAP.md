# Roadmap

This is the direction, not a promise with dates attached. Self-hosted software for a small team moves in bursts, not sprints. What follows is grouped by how close each thing is to being real, not by quarter.

If you're looking for where to jump in as a contributor, the "Now" and "Next" sections are the best places to look — see also [`FEATURES.md`](./FEATURES.md) for a more granular, issue-sized breakdown, and the [Project board](https://github.com/orgs/NeuralOPS-Nexus/projects/3) for what's actively claimed.

## Now

**Team & permissions, made consistent.** Nexus's permission model — Owner, Admin, Member, Viewer, at company, project, and topic scope — is documented in `CONCEPTS-AND-ROLES.md`, and it's more thought-through than most self-hosted tools bother with. But enforcement doesn't yet apply the same way on every path a person can join a company, project, or topic. Bringing every membership path (invite, acceptance, topic-scoped invites) up to the same standard the core RBAC engine already documents is the current top priority — before anything else, because it's the foundation everything about "humans and AI personas side by side, safely scoped" sits on.

**Self-host stability.** The single-image deployment (`docker-compose.neuralops.yaml`, nine containers, one shared image) is working end-to-end, but it's young. Making it boringly reliable across more host environments — different reverse proxy setups, different RAM budgets, clearer error messages when a secret or env var is missing — matters more right now than new surface area.

## Next

**Multi-tool personas.** Today a persona's agent is wired to exactly one MCP server — the relationship is a single database field, not a UI limit. Letting a persona reach multiple tools at once means reworking how an Agent attaches to MCP Servers (closer to a many-to-many, with its own attach/detach flow, than a config change). This is one of the most-requested shapes of "make the AI more useful" and it's a real architecture project, not a quick add.

**OAuth for tool connections.** Every tool integration today authenticates with an API token, stored encrypted. Some tools a team wants to connect either don't offer token auth or strongly prefer OAuth — supporting it means a token-refresh and consent model that doesn't exist yet.

**A wider tool library, community-built.** The `mcps/` folder ships three example MCP servers (SerpAPI, Odoo ERP, filesystem) as a pattern, not a ceiling. Because MCP servers are their own standalone service — you write one without touching Nexus's core — this is the single easiest way to contribute something a real team will actually use. Slack, GitHub, Notion, Linear, a CRM, an internal wiki: if your team already has an MCP server for it (or wants one), it plugs in the same way filesystem and monday.com do today.

**Project-scoped persona and model permissions.** Personas and AI Models are currently company-scope-only for creation — deliberately more conservative than Agents/MCP Servers, which got moved to project scope so a Project Admin can manage them without company-wide access. Whether Personas deserve the same treatment, or whether company-scope-only is the right permanent answer given they touch system prompts and model access, is an open design question worth community input on.

## Later

**Load and scale.** Nexus hasn't been tested past a handful of concurrent users. Before recommending it for a larger team, it needs real multi-user, multi-topic load testing — and probably some tuning of Celery/Centrifugo concurrency as a result.

**Richer knowledge bases.** Today's context model is a solid foundation — per-topic `ContextSource` for one-off files/URLs, company-wide `KnowledgeBase` for anything meant to be reused across projects and conversations. Deeper retrieval quality, better handling of large document sets, and easier curation of what a persona can see are all open territory on top of it.

**More output directives.** `@chart`, `@table`, `@diagram`, `@form`, `@code`, `@terminal`, `@html` cover a lot of ground already. More directive types, and better composability between them (a form that submits into a chart, for instance), are a natural next step once the current set has more real-world mileage.

---

Have an opinion on sequencing, or want to propose something not listed here? Open a discussion or a Project-board issue — this roadmap is meant to be argued with, not just read.
