# Rules for whoever implements in this module (human or model)

This module is the **rebuilt nexus-ai**. Its prompt is
`docs/NEXUS-AI-REVAMP.md` — §1.1–§1.5 are the law; where older sections
disagree, §1.1–§1.5 win. The old code lives at `modules/nexus-ai-legacy/` and
is **reference only**.

## Hard rules

1. **Work one layer (or one item) at a time**; each is reviewed before the next.
2. **Do not add files or classes outside the agreed structure** (§1.5 folder
   structure and class catalog). **Do not change a signature without asking.**
3. **No imports from `modules/nexus-ai-legacy/`.** Code may be copied only when
   accepted as a copy candidate; it then belongs to this module, with its tests.
4. **Pinned library versions only** (`requirements.txt`, frozen in
   `requirements.lock`). Confirm every pydantic-ai / harness name you use
   against the pinned version before building on it.
5. **Write the acceptance tests first**; "done" means they pass:
   `pip install -r requirements-dev.txt && python -m pytest`.

## Dependency rules (checked by tests/test_dependencies.py — T16)

- `fastapi_app` imports `ai_engine`. `ai_engine` imports only
  `fastapi_app/contracts` — never FastAPI or Django.
- Only `ai_engine/pydantic_ai_system/` (including its `tools/`) imports
  pydantic-ai or pydantic-ai-harness.
- Only `NucleusClient` calls nucleus.
- Only `ai_engine/vector_db/` will touch pgvector or txtai (Layer 3).
- The router makes one call into the AI system; the steps of a reply live in
  `PydanticAISystem`.
- `fastapi_app/__init__.py` stays empty of imports — `ai_engine` pulls
  `fastapi_app.contracts` in, and anything imported there would come with it.

## Invariants that must always hold

- Every field nucleus sends has a place.
- The system prompt is sent **once**, through **`instructions=`, never
  `system_prompt=`** (pydantic-ai drops system_prompt whenever message history
  is passed — verified on 2.55.0).
- `context_window` and the persona's output limit are **never the same field**.
- Usage is recorded on **every ending** — done, stop, failure.
- Cached tokens are never priced at the input rate; reasoning is never added
  on top of output (it is already inside `output_tokens`).
- Every stream ends with **exactly one final event** (while the client is
  connected); a crash becomes one clean `message_error`, never a dropped
  connection.
- Write tools always ask (from Layer 1 on).
- Exact money arithmetic: `Decimal`, never float (`ai_engine/core/billing.py`
  pins the formula; O1 puts the production price table in nucleus).
- `PYDANTIC_AI_NO_BANNER=1` in the service environment.

## Layer 0 status

Layer 0 (items 25, 7, 26, 15*, 37, 21, 47-feed) is built and green:
T1–T16 in `tests/`. Fakes: `tests/fake_provider.py` answers like OpenAI's and
Anthropic's streaming APIs and records every request body;
`tests/fake_nucleus.py` serves persona/history and records usage posts.

*15 in its Layer 0 form: stable-first instructions, system prompt once; the
summary anchor and budget fitting come with items 6 and 16.

## nucleus changes Layer 0 expects (separate handoff — none block a plain reply)

1. New usage endpoint `POST /api/v1/internal/usage/` taking `{"records": [...]}`
   (UsageRecord fields, `called_at` ISO, `cost` null) — pricing on arrival (O1),
   topic totals + live push (item 47).
2. History endpoint: a `status` field per row; rows only after the topic's last
   compaction (O3). Until then: no status filter applies (rows pass), which is
   0.8.0 behaviour.
3. Model roles — mapped on this side in `NucleusClient.persona_from` until
   nucleus has roles.
4. `company_id`, `project_id`, `user_id` in the trigger payload (O2). Until
   then they default to "" and usage records carry "".
5. One internal-key header name both ways: `X-Internal-Key` (O5).
   `NucleusClient` sends both spellings meanwhile, so it works against
   today's nucleus unchanged.
