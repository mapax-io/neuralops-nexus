# Vision

NeuralOps Nexus is a self-hosted team workspace where AI personas are members of a project, not a tab you switch to.

Most "AI in the workplace" products today are one of two shapes: a chatbot bolted onto the side of your existing tools, or a SaaS platform that asks you to move your team's conversations, files, and API keys onto someone else's servers so their AI can reach them. Neither shape fits a team that wants AI woven into how they actually work together, without handing a third party the keys to their files, their model provider account, and their internal conversations.

Nexus is built on three commitments, and they're the test every feature has to pass:

**AI in the flow of work, not in another tab.** A persona is a member of your project team. It sits in the same Projects → Channels → Topics structure your humans do, it's `@mention`ed the same way a person is, and it can be asked to shape its answer with a directive — a chart, a table, a diagram, a form, runnable code, a terminal, rendered HTML — instead of always producing a wall of text back at you.

**AI that reads your actual files and connects to your actual tools.** A persona isn't limited to what you paste into a prompt. Through MCP, it can be wired to your filesystem, your project management tool, your ERP, whatever your team already runs on — and because MCP servers are configuration, not code, connecting a new tool to a persona doesn't require anyone to ship a new build of Nexus.

**Runs on infrastructure you control.** One Docker image, your server, your model provider keys. Nothing leaves your infrastructure unless you explicitly configure it to. This isn't a compliance checkbox — it's the actual reason a "team workspace with AI teammates" can be trusted with the kind of internal, sensitive, half-finished work that people are usually careful about putting in front of any outside AI product.

## Why this is open source

Self-hosted-and-trust-us doesn't work — the whole pitch of running this on your own infrastructure falls apart if you can't verify what it's actually doing with your data and your model keys. Being open source is what makes "nothing leaves your server unless you configure it to" a claim you can check, not just a claim we make. Anyone can read the code path from a chat message to a model API call, from a persona to the tools it's connected to, and confirm there's no phone-home behavior hiding in it.

It's also the only realistic way to build the thing this project is actually betting on: a wide library of tools a persona can be connected to. MCP was chosen specifically because adding a new tool integration is writing an MCP server, not touching Nexus's core — which means the community can grow the tool library faster than any single team could, the same way the `mcps/` folder already ships example servers (SerpAPI, Odoo ERP, filesystem) as a starting pattern to build from, not a closed list.

## Who this is for

Teams who want an AI teammate in their actual workflow, not a separate AI product they have to remember to go use — and who care enough about where their data and model spend goes that "we'll host it for you" isn't an acceptable answer. In practice: engineering teams running release channels with an AI that can read the repo and open PRs; go-to-market teams with an AI that can pull from their CRM and draft in the channel where the deal is actually being discussed; anyone self-hosting internal tools already, for whom Nexus is one more service in a stack they already run, not a new vendor relationship.

## What "done" looks like

Never fully done — but the shape we're building toward is a workspace where adding an AI teammate to a project is as unremarkable as adding a human one: pick a model, pick the tools it needs, invite it, and it just works inside the same conversations, permissions, and context your team already has. The gap between that and where the project is today is most of what the roadmap and feature list below are about.
