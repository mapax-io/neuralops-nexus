# Security Policy

NeuralOps Nexus runs on your own server and holds your team's conversations,
files and model provider keys, so we take security reports seriously.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | ✅ security fixes |
| < 1.0 | ❌ please upgrade |

Security fixes ship as patch releases of the Docker image
(`noamanfaisal/neuralops`) and are listed in the release notes.

## Reporting a vulnerability

**Please do not open a public issue, discussion or pull request for a
security problem.**

Report it privately through GitHub:
**Security tab → "Report a vulnerability"**
([direct link](https://github.com/mapax-io/neuralops-nexus/security/advisories/new)).
Only the maintainers can see the report.

Helpful to include:

- the version / image tag you're running (`NEURALOPS_VERSION`)
- what an attacker can do, and what they need first (an account? a persona
  with tools? network access to the server?)
- steps to reproduce or a proof of concept
- any logs, with keys and personal data removed

## What to expect

- **Acknowledgement** within 5 business days.
- **An initial assessment** (confirmed / not a vulnerability / need more
  info) within 10 business days.
- **A fix and advisory** for confirmed issues, coordinated with you. We'll
  credit you in the advisory unless you'd rather stay anonymous.

Please give us a reasonable chance to ship a fix before disclosing publicly.

## In scope

- the backend in this repository: nucleus (Django), the nexus-ai engine
  (FastAPI), the MCP gateway, the rights/permissions system, real-time
  transport configuration, and the published Docker image
- authentication and authorization bypasses, cross-project or cross-company
  data exposure, leaks of stored provider keys or MCP secrets, injection,
  SSRF through MCP tools or connectors, and persona/tool actions that escape
  their granted rights

## Out of scope

- vulnerabilities in third-party MCP servers or model providers themselves
  (report those upstream; tell us if NeuralOps makes them worse)
- issues that require an already-compromised server or the owner's own
  credentials
- missing hardening on a deployment the operator configured insecurely
  (for example, exposing Postgres to the internet against the self-host guide)
- denial of service by volume, and social engineering

## Running it safely

- Generate per-deployment secrets once with
  `docker run --rm <image> init-secrets > neuralops/secrets.env` and never
  commit that file.
- Keep Postgres, Redis and the internal service ports off the public
  internet; expose only the nginx entry point.
- Keep the image up to date.
