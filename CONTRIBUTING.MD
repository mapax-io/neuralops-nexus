# Contributing to NeuralOps Nexus

Thank you for your interest in contributing. Before we can accept a pull
request, every contributor needs to agree to the Contributor License
Agreement (CLA) below — this is a one-time step per contributor, usually
handled automatically by a CLA bot the first time you open a PR.

## Why a CLA

NeuralOps Nexus is released under the NeuralOps Nexus Source Available
License 1.0, and is also available under a separate commercial license
for organizations that need terms it doesn't offer. To keep that
dual-licensing model working — and to keep the project's licensing
position clean for anyone who wants to rely on it — every contribution
needs to come with clear rights attached, not just an implicit "I put
this in a pull request." The CLA below is what provides that.

**Important:** this CLA covers contributions made *after* you agree to
it. It does not retroactively apply to code already in the repository
from before this policy was adopted.

## Individual Contributor License Agreement

By submitting a contribution (a pull request, patch, or similar) to the
NeuralOps Nexus project, you agree to the following terms:

1. **Grant of rights.** You grant Noaman Faisal Bin (the "Maintainer") a
   perpetual, worldwide, non-exclusive, royalty-free, irrevocable license
   to use, reproduce, modify, prepare derivative works of, publicly
   display, publicly perform, sublicense, and distribute your
   contribution, and to relicense it — including under different terms
   than the Project's current license, such as AGPL-3.0, a fully
   permissive license, or a commercial/proprietary license — at the
   Maintainer's sole discretion. For clarity, this includes using your
   contribution in the Project's closed-source commercial offerings
   (including its hosted SaaS, Enterprise, and mobile applications),
   which are licensed separately from, and under different terms than,
   the Project's own release.

2. **Copyright.** You retain copyright ownership of your contribution.
   This is a license grant, not an assignment: you're not giving up
   ownership, you're confirming the Maintainer can use and relicense
   what you submit.

3. **Originality.** You confirm that each contribution is your own
   original work, or that you otherwise have the right to submit it
   under these terms (for example, it isn't owned by an employer who
   hasn't authorized you to contribute it).

4. **Patents.** You grant the Maintainer and all recipients of software
   distributed under this project a perpetual, worldwide, non-exclusive,
   royalty-free patent license to make, use, sell, and distribute your
   contribution, for any patent claims you own or control that are
   necessarily infringed by your contribution alone or in combination
   with the project.

5. **No obligation.** You understand the Maintainer is under no
   obligation to use or incorporate your contribution.

## How this gets signed in practice

Rather than asking every contributor to sign a document by hand, this is
typically wired up through a CLA bot (e.g., cla-assistant.io or a GitHub
Action) that posts the text above on a contributor's first pull request
and records a lightweight "I agree" click. Set this up before opening the
repository to outside contributions — a CLA that's only aspirational in a
markdown file, with no actual gate on merging, doesn't protect the
dual-licensing model.

## Code of conduct

Be respectful and constructive. Harassment, personal attacks, and
discriminatory language aren't tolerated. If you experience or witness
unacceptable behavior in this project's spaces, report it to
[maintainer contact email]. *(Consider adopting the [Contributor
Covenant](https://www.contributor-covenant.org/) wholesale if you want a
more complete, standard policy rather than this short version.)*

## Before you start

- For anything beyond a small fix (a new feature, a behavior change, a
  refactor), open an issue first to discuss the approach before writing
  code. This saves you from a large PR being redirected or declined after
  the work is already done.
- Check open issues and PRs first so you're not duplicating in-flight
  work.

## Development setup

1. Fork the repository and clone your fork.
2. Copy `.env.example` to `.env` and fill in required values.
3. `docker compose up` to bring up the local dev stack (`nucleus`,
   `nexus-ai`, the local dev frontend, Postgres, Redis, ChromaDB).
4. Run the test suite before making changes, to confirm your environment
   is clean: *(add the actual command, e.g. `docker compose exec nucleus
   pytest`)*.

## Making changes

- **Branch naming:** `feature/short-description`, `fix/short-description`,
  or `docs/short-description`.
- **Commit messages:** a short, imperative summary line (e.g. "Fix rate
  limit bug in nexus-ai router"), with more detail in the body if the
  change isn't self-explanatory.
- **Backend (Django / FastAPI / pydantic-ai):** follow existing project
  conventions for models, routers, and services; run the linter/formatter
  before committing *(name the actual tools in use, e.g. `ruff`, `black`,
  `mypy`)*.
- **Frontend (React / TanStack Start):** match existing component and
  state-management patterns; run `npm run lint` and `npm run typecheck`
  before committing.
- **Tests:** new behavior needs a test; bug fixes should include a test
  that would have caught the bug. PRs that reduce test coverage without a
  stated reason will be asked to add coverage back.

## Submitting a pull request

1. Open the PR against `main` *(or your actual default branch)*, with a
   clear description of what changed and why.
2. Link the issue it addresses, if any.
3. The CLA bot will prompt you to accept the CLA above on your first PR —
   this is required before the PR can be merged.
4. Expect at least one maintainer review; be responsive to review
   comments so the PR doesn't stall.
5. Squash-merge is the default once approved *(adjust to your actual
   merge policy)*.

## Reporting bugs and requesting features

Use GitHub Issues. For bugs, include: steps to reproduce, expected vs.
actual behavior, and relevant logs/environment details (Docker version,
OS, browser if frontend-related). For feature requests, describe the
problem you're trying to solve, not just the solution you have in mind —
it's easier to evaluate and sometimes there's a simpler existing path.

## Security issues

Do not open a public issue for a security vulnerability. Email
[security contact email] instead, and allow reasonable time for a fix
before any public disclosure.
