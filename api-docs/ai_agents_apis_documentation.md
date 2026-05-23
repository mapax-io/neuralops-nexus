# 13. AI Agent APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/agents |
| POST | /api/v1/agents |
| GET | /api/v1/agents/{agent_id} |
| PATCH | /api/v1/agents/{agent_id} |
| DELETE | /api/v1/agents/{agent_id} |
| POST | /api/v1/agents/{agent_id}/test |
| POST | /api/v1/agents/{agent_id}/run |
| POST | /api/v1/agents/{agent_id}/cancel-run |
| GET | /api/v1/agents/{agent_id}/runs |
| GET | /api/v1/agents/{agent_id}/runs/{run_id} |
| GET | /api/v1/agents/{agent_id}/runs/{run_id}/steps |
| GET | /api/v1/agents/{agent_id}/runs/{run_id}/logs |

---

## 13.1 GET /api/v1/agents

### Detail

Returns a paginated list of all AI Agents belonging to the authenticated user's active company. Supports optional filtering by agent type and active status. Only agents scoped to `request.auth.current_company` are returned.

### Flow

1. Authenticate request via JWT; resolve `current_company` from user.
2. Query `AIAgent` filtered by `company`, `is_active=True`.
3. Apply optional query filters (`agent_type`, `search`).
4. Return paginated list of agent summaries.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/agents?agent_type=internal&page=1&page_size=20
{
  "agent_type": "internal",   // optional: "internal" | "external"
  "search": "support",        // optional: name search
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Support Agent",
      "description": "Handles customer support queries",
      "agent_type": "internal",
      "is_active": true,
      "safety_mode": true,
      "max_steps": 5,
      "allow_parallel_tools": false,
      "model": {
        "id": "m1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "GPT-4o",
        "provider": "openai"
      },
      "mcp_server": null,
      "created_at": "2026-05-01T10:00:00Z",
      "updated_at": "2026-05-10T12:00:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class AIModelBriefOut(Schema):
    id: UUID
    name: str
    provider: str


class MCPServerBriefOut(Schema):
    id: UUID
    name: str
    server_type: str


class AgentListItemOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    agent_type: str
    is_active: bool
    safety_mode: bool
    max_steps: int
    allow_parallel_tools: bool
    model: Optional[AIModelBriefOut]
    mcp_server: Optional[MCPServerBriefOut]
    created_at: datetime
    updated_at: datetime


class AgentListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[AgentListItemOut]


class AgentFilterSchema(Schema):
    agent_type: Optional[str] = None
    search: Optional[str] = None
```

### Models Involved

- `AIAgent` — primary model
- `AIModel` — FK for `model` (nested brief)
- `MCPServer` — FK for `mcp_server` (nested brief)
- `Company` — tenant scope filter

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent

def list_agents(request, filters):
    qs = AIAgent.objects.filter(
        company=request.auth.current_company,
        is_active=True,
    ).select_related("model", "mcp_server")

    if filters.agent_type:
        qs = qs.filter(agent_type=filters.agent_type)

    if filters.search:
        qs = qs.filter(name__icontains=filters.search)

    return qs.order_by("-created_at")
```

---

## 13.2 POST /api/v1/agents

### Detail

Creates a new AI Agent in the authenticated user's active company. Requires at minimum a `name` and `agent_type`. Internal agents require a linked `model_id`. External agents require an `external_url`. The creating user is implicitly associated as the owner through the company scope.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate payload (enforce `internal_agent_requires_model` and `external_agent_requires_url` constraints).
3. Verify `model_id` belongs to same company (if internal).
4. Verify `mcp_server_id` belongs to same company (if provided).
5. Create and return the new `AIAgent` record.

### Request JSON

```json
{
  "name": "Research Agent",
  "description": "Performs web research and summarization",
  "agent_type": "internal",
  "system_prompt": "You are a research assistant. Always cite your sources.",
  "model_id": "m1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "mcp_server_id": null,
  "safety_mode": true,
  "max_steps": 10,
  "allow_parallel_tools": true
}
```

### Response JSON

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "Research Agent",
  "description": "Performs web research and summarization",
  "agent_type": "internal",
  "external_url": null,
  "system_prompt": "You are a research assistant. Always cite your sources.",
  "safety_mode": true,
  "max_steps": 10,
  "allow_parallel_tools": true,
  "is_active": true,
  "model": {
    "id": "m1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "GPT-4o",
    "provider": "openai"
  },
  "mcp_server": null,
  "created_at": "2026-05-22T08:00:00Z",
  "updated_at": "2026-05-22T08:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class AgentCreateIn(Schema):
    name: str
    description: Optional[str] = None
    agent_type: str  # "internal" | "external"
    system_prompt: Optional[str] = None
    model_id: Optional[UUID] = None
    mcp_server_id: Optional[UUID] = None
    external_url: Optional[str] = None
    secret_ref: Optional[str] = None
    safety_mode: bool = True
    max_steps: int = 5
    allow_parallel_tools: bool = False


class AgentDetailOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    agent_type: str
    external_url: Optional[str]
    system_prompt: Optional[str]
    safety_mode: bool
    max_steps: int
    allow_parallel_tools: bool
    is_active: bool
    model: Optional[AIModelBriefOut]
    mcp_server: Optional[MCPServerBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AIAgent` — created record
- `AIModel` — FK validated and nested
- `MCPServer` — FK validated and nested (optional)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AIModel, MCPServer
from ninja.errors import HttpError

def create_agent(request, payload: AgentCreateIn):
    company = request.auth.current_company

    model = None
    if payload.model_id:
        model = AIModel.objects.get(id=payload.model_id, company=company)

    mcp_server = None
    if payload.mcp_server_id:
        mcp_server = MCPServer.objects.get(id=payload.mcp_server_id, company=company)

    agent = AIAgent.objects.create(
        company=company,
        name=payload.name,
        description=payload.description,
        agent_type=payload.agent_type,
        system_prompt=payload.system_prompt,
        model=model,
        mcp_server=mcp_server,
        external_url=payload.external_url,
        secret_ref=payload.secret_ref,
        safety_mode=payload.safety_mode,
        max_steps=payload.max_steps,
        allow_parallel_tools=payload.allow_parallel_tools,
    )
    return agent
```

---

## 13.3 GET /api/v1/agents/{agent_id}

### Detail

Retrieves the full detail of a single AI Agent by its UUID. The agent must belong to the authenticated user's active company. Returns all configuration fields including linked model and MCP server details.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `AIAgent` by `agent_id` scoped to `company`.
3. Return 404 if not found or soft-deleted.
4. Return full agent detail with nested relations.

### Request JSON

```json
// No request body — agent_id is a path parameter
// GET /api/v1/agents/b2c3d4e5-f6a7-8901-bcde-f12345678901
```

### Response JSON

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "Research Agent",
  "description": "Performs web research and summarization",
  "agent_type": "internal",
  "external_url": null,
  "system_prompt": "You are a research assistant. Always cite your sources.",
  "safety_mode": true,
  "max_steps": 10,
  "allow_parallel_tools": true,
  "is_active": true,
  "model": {
    "id": "m1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "GPT-4o",
    "provider": "openai",
    "model_id": "gpt-4o",
    "supports_tools": true,
    "supports_streaming": true
  },
  "mcp_server": null,
  "created_at": "2026-05-22T08:00:00Z",
  "updated_at": "2026-05-22T08:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class AIModelDetailOut(Schema):
    id: UUID
    name: str
    provider: str
    model_id: str
    supports_tools: bool
    supports_streaming: bool


class MCPServerDetailOut(Schema):
    id: UUID
    name: str
    server_type: str
    transport: str
    url: Optional[str]


class AgentDetailOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    agent_type: str
    external_url: Optional[str]
    system_prompt: Optional[str]
    safety_mode: bool
    max_steps: int
    allow_parallel_tools: bool
    is_active: bool
    model: Optional[AIModelDetailOut]
    mcp_server: Optional[MCPServerDetailOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AIAgent` — primary record
- `AIModel` — FK `model` (nested detail)
- `MCPServer` — FK `mcp_server` (nested detail)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent
from ninja.errors import HttpError

def get_agent(request, agent_id):
    try:
        return AIAgent.objects.select_related(
            "model", "mcp_server"
        ).get(
            id=agent_id,
            company=request.auth.current_company,
            is_active=True,
        )
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")
```

---

## 13.4 PATCH /api/v1/agents/{agent_id}

### Detail

Partially updates an existing AI Agent. Only fields provided in the request body are updated. Enforces the same model/URL constraints as creation. The agent must belong to the authenticated user's active company.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `AIAgent` by `agent_id` scoped to `company`.
3. Validate any new `model_id` or `mcp_server_id` belongs to same company.
4. Apply only the provided fields (partial update).
5. Save and return updated agent detail.

### Request JSON

```json
{
  "name": "Research Agent v2",
  "system_prompt": "You are a research assistant. Always cite sources. Be concise.",
  "max_steps": 15,
  "safety_mode": false
}
```

### Response JSON

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "Research Agent v2",
  "description": "Performs web research and summarization",
  "agent_type": "internal",
  "external_url": null,
  "system_prompt": "You are a research assistant. Always cite sources. Be concise.",
  "safety_mode": false,
  "max_steps": 15,
  "allow_parallel_tools": true,
  "is_active": true,
  "model": {
    "id": "m1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "GPT-4o",
    "provider": "openai",
    "model_id": "gpt-4o",
    "supports_tools": true,
    "supports_streaming": true
  },
  "mcp_server": null,
  "created_at": "2026-05-22T08:00:00Z",
  "updated_at": "2026-05-22T09:30:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class AgentUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[UUID] = None
    mcp_server_id: Optional[UUID] = None
    external_url: Optional[str] = None
    secret_ref: Optional[str] = None
    safety_mode: Optional[bool] = None
    max_steps: Optional[int] = None
    allow_parallel_tools: Optional[bool] = None
    is_active: Optional[bool] = None
```

### Models Involved

- `AIAgent` — updated record
- `AIModel` — optional FK re-assignment validation
- `MCPServer` — optional FK re-assignment validation
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AIModel, MCPServer
from ninja.errors import HttpError

def update_agent(request, agent_id, payload: AgentUpdateIn):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    update_fields = []

    for field in ["name", "description", "system_prompt", "external_url",
                  "secret_ref", "safety_mode", "max_steps", "allow_parallel_tools", "is_active"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(agent, field, value)
            update_fields.append(field)

    if payload.model_id is not None:
        agent.model = AIModel.objects.get(id=payload.model_id, company=company)
        update_fields.append("model")

    if payload.mcp_server_id is not None:
        agent.mcp_server = MCPServer.objects.get(id=payload.mcp_server_id, company=company)
        update_fields.append("mcp_server")

    if update_fields:
        agent.save(update_fields=update_fields + ["updated_at"])

    return agent
```

---

## 13.5 DELETE /api/v1/agents/{agent_id}

### Detail

Soft-deletes an AI Agent by setting `is_active=False` and recording `deleted_at`. The agent must belong to the authenticated user's active company. Any active runs for this agent are not automatically cancelled; this must be handled explicitly before deletion.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `AIAgent` by `agent_id` scoped to `company`.
3. Check there are no running `AgentRun` records for this agent (optional guard).
4. Call `agent.soft_delete()`.
5. Return 204 No Content.

### Request JSON

```json
// No request body — agent_id is a path parameter
// DELETE /api/v1/agents/b2c3d4e5-f6a7-8901-bcde-f12345678901
```

### Response JSON

```json
// 204 No Content
```

### Pydantic for Django Ninja

```python
# No input or output schema required.
# Return HTTP 204 using Django Ninja's response={204: None} pattern.
```

### Models Involved

- `AIAgent` — soft-deleted record
- `AgentRun` — checked for active runs (guard)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun
from ninja.errors import HttpError

def delete_agent(request, agent_id):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    active_runs = AgentRun.objects.filter(
        agent=agent,
        status__in=["pending", "running", "waiting_approval"],
    ).exists()

    if active_runs:
        raise HttpError(409, "Cannot delete agent with active runs. Cancel runs first.")

    agent.soft_delete()
    return None
```

---

## 13.6 POST /api/v1/agents/{agent_id}/test

### Detail

Runs a quick synchronous smoke-test against the agent using a provided test prompt. Validates that the underlying model is reachable and the agent can produce a basic response. Does not create an `AgentRun` record. Primarily used during agent setup to verify configuration is correct.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `AIAgent` with model/mcp_server.
3. Validate agent is active and properly configured.
4. Send `test_prompt` to the underlying `AIModel` (via LiteLLM) or to `external_url`.
5. Return a brief test result with response preview.

### Request JSON

```json
{
  "test_prompt": "Say hello and tell me your role in one sentence.",
  "timeout_seconds": 15
}
```

### Response JSON

```json
{
  "success": true,
  "agent_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "agent_name": "Research Agent v2",
  "test_prompt": "Say hello and tell me your role in one sentence.",
  "response_preview": "Hello! I'm a research assistant here to help you find and summarize information with cited sources.",
  "latency_ms": 832,
  "model_used": "gpt-4o",
  "error": null
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class AgentTestIn(Schema):
    test_prompt: str
    timeout_seconds: int = 15


class AgentTestOut(Schema):
    success: bool
    agent_id: UUID
    agent_name: str
    test_prompt: str
    response_preview: Optional[str]
    latency_ms: Optional[int]
    model_used: Optional[str]
    error: Optional[str]
```

### Models Involved

- `AIAgent` — configuration source
- `AIModel` — used to make test inference call
- `MCPServer` — optionally tested for connectivity

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent
from ninja.errors import HttpError
import time

def test_agent(request, agent_id, payload: AgentTestIn):
    try:
        agent = AIAgent.objects.select_related("model", "mcp_server").get(
            id=agent_id,
            company=request.auth.current_company,
            is_active=True,
        )
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    if agent.agent_type == "internal" and agent.model is None:
        raise HttpError(422, "Internal agent has no model configured.")

    # Invoke AI service layer (LiteLLM / external URL) — not ORM
    start = time.time()
    try:
        response = ai_service.quick_test(agent, payload.test_prompt, payload.timeout_seconds)
        latency_ms = int((time.time() - start) * 1000)
        return AgentTestOut(
            success=True,
            agent_id=agent.id,
            agent_name=agent.name,
            test_prompt=payload.test_prompt,
            response_preview=response[:500],
            latency_ms=latency_ms,
            model_used=agent.model.model_id if agent.model else None,
            error=None,
        )
    except Exception as exc:
        return AgentTestOut(
            success=False,
            agent_id=agent.id,
            agent_name=agent.name,
            test_prompt=payload.test_prompt,
            response_preview=None,
            latency_ms=None,
            model_used=None,
            error=str(exc),
        )
```

---

## 13.7 POST /api/v1/agents/{agent_id}/run

### Detail

Triggers a new agent execution (run) for the given agent. Requires an input payload describing the task or message for the agent. Creates an `AgentRun` record scoped to the company, project, and optionally a chat topic. The run may execute synchronously (for short tasks) or asynchronously (for long-running or multi-step tasks). Returns the created `AgentRun` immediately with `status: pending`.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch and validate `AIAgent`.
3. Validate `project_id` belongs to same company.
4. Create `AgentRun` record with `status: pending`.
5. Dispatch run to agent execution worker (async task queue).
6. Return the created `AgentRun` object.

### Request JSON

```json
{
  "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "input": {
    "message": "Research the latest advancements in quantum computing and produce a 3-paragraph summary.",
    "context": {
      "language": "en",
      "max_length": 500
    }
  }
}
```

### Response JSON

```json
{
  "id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "agent_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "input_payload": {
    "message": "Research the latest advancements in quantum computing and produce a 3-paragraph summary.",
    "context": { "language": "en", "max_length": 500 }
  },
  "output_payload": {},
  "error": null,
  "started_at": null,
  "completed_at": null,
  "triggered_by": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "noaman@example.com"
  },
  "created_at": "2026-05-22T09:00:00Z",
  "updated_at": "2026-05-22T09:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class AgentRunIn(Schema):
    project_id: UUID
    topic_id: Optional[UUID] = None
    input: dict[str, Any]


class UserBriefOut(Schema):
    id: UUID
    username: str


class AgentRunOut(Schema):
    id: UUID
    agent_id: UUID
    project_id: UUID
    topic_id: Optional[UUID]
    status: str
    input_payload: dict
    output_payload: dict
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    triggered_by: Optional[UserBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AgentRun` — created execution record
- `AIAgent` — resolved agent configuration
- `Project` — FK validated and scoped
- `ChatTopic` — optional FK for topic-linked runs
- `User` — `triggered_by` (auth user)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun, Project, ChatTopic
from ninja.errors import HttpError

def run_agent(request, agent_id, payload: AgentRunIn):
    company = request.auth.current_company
    user = request.auth

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    try:
        project = Project.objects.get(id=payload.project_id, company=company, is_active=True)
    except Project.DoesNotExist:
        raise HttpError(404, "Project not found.")

    topic = None
    if payload.topic_id:
        try:
            topic = ChatTopic.objects.get(id=payload.topic_id, company=company, is_active=True)
        except ChatTopic.DoesNotExist:
            raise HttpError(404, "Topic not found.")

    run = AgentRun.objects.create(
        company=company,
        project=project,
        agent=agent,
        topic=topic,
        triggered_by=user,
        input_payload=payload.input,
        status="pending",
    )

    # Dispatch to async worker (Celery / background task)
    dispatch_agent_run.delay(run.id)

    return run
```

---

## 13.8 POST /api/v1/agents/{agent_id}/cancel-run

### Detail

Cancels an in-progress or pending `AgentRun` for the given agent. The run must be in a cancellable state (`pending`, `running`, or `waiting_approval`). Sends a cancellation signal to the worker and updates the run's status to `cancelled`. No new steps will be created after cancellation.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `agent_id` belongs to company.
3. Fetch `AgentRun` by `run_id` (from request body) scoped to agent + company.
4. Check run is in a cancellable state.
5. Signal worker to stop (e.g. Redis flag, Celery revoke).
6. Update `AgentRun.status = "cancelled"`.
7. Return updated run object.

### Request JSON

```json
{
  "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "reason": "User requested cancellation"
}
```

### Response JSON

```json
{
  "id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "agent_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "status": "cancelled",
  "error": "Cancelled by user: User requested cancellation",
  "started_at": "2026-05-22T09:00:05Z",
  "completed_at": "2026-05-22T09:00:47Z",
  "updated_at": "2026-05-22T09:00:47Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class AgentCancelRunIn(Schema):
    run_id: UUID
    reason: Optional[str] = None


class AgentRunCancelOut(Schema):
    id: UUID
    agent_id: UUID
    status: str
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    updated_at: datetime
```

### Models Involved

- `AgentRun` — status updated to `cancelled`
- `AIAgent` — ownership validated
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun
from ninja.errors import HttpError
from django.utils import timezone

CANCELLABLE_STATUSES = ["pending", "running", "waiting_approval"]

def cancel_agent_run(request, agent_id, payload: AgentCancelRunIn):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    try:
        run = AgentRun.objects.get(
            id=payload.run_id,
            agent=agent,
            company=company,
        )
    except AgentRun.DoesNotExist:
        raise HttpError(404, "Run not found.")

    if run.status not in CANCELLABLE_STATUSES:
        raise HttpError(409, f"Cannot cancel run with status '{run.status}'.")

    # Signal worker to stop
    cancel_worker_task.delay(str(run.id))

    run.status = "cancelled"
    run.error = f"Cancelled by user: {payload.reason}" if payload.reason else "Cancelled by user."
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error", "completed_at", "updated_at"])

    return run
```

---

## 13.9 GET /api/v1/agents/{agent_id}/runs

### Detail

Returns a paginated list of all `AgentRun` records for the given agent, filtered by company. Supports optional filtering by status and date range. Most recent runs are returned first.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `agent_id` belongs to company.
3. Query `AgentRun` filtered by `agent` + `company`.
4. Apply optional filters (`status`, `project_id`, `from_date`, `to_date`).
5. Return paginated list.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/agents/{agent_id}/runs?status=completed&page=1&page_size=20
{
  "status": "completed",
  "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "from_date": "2026-05-01",
  "to_date": "2026-05-22",
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 12,
  "next": "http://api/v1/agents/{agent_id}/runs?page=2",
  "previous": null,
  "results": [
    {
      "id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "agent_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "completed",
      "error": null,
      "started_at": "2026-05-22T09:00:05Z",
      "completed_at": "2026-05-22T09:01:33Z",
      "triggered_by": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "noaman@example.com"
      },
      "created_at": "2026-05-22T09:00:00Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema, FilterSchema
from typing import Optional
from uuid import UUID
from datetime import datetime, date


class AgentRunFilterSchema(FilterSchema):
    status: Optional[str] = None
    project_id: Optional[UUID] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None


class AgentRunListItemOut(Schema):
    id: UUID
    agent_id: UUID
    project_id: UUID
    topic_id: Optional[UUID]
    status: str
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    triggered_by: Optional[UserBriefOut]
    created_at: datetime


class AgentRunListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[AgentRunListItemOut]
```

### Models Involved

- `AgentRun` — primary listing model
- `AIAgent` — parent, ownership scope
- `Project` — optional filter
- `User` — `triggered_by` nested
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun
from ninja.errors import HttpError

def list_agent_runs(request, agent_id, filters: AgentRunFilterSchema):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    qs = AgentRun.objects.filter(
        agent=agent,
        company=company,
    ).select_related("triggered_by")

    if filters.status:
        qs = qs.filter(status=filters.status)

    if filters.project_id:
        qs = qs.filter(project_id=filters.project_id)

    if filters.from_date:
        qs = qs.filter(created_at__date__gte=filters.from_date)

    if filters.to_date:
        qs = qs.filter(created_at__date__lte=filters.to_date)

    return qs.order_by("-created_at")
```

---

## 13.10 GET /api/v1/agents/{agent_id}/runs/{run_id}

### Detail

Retrieves the full detail of a single `AgentRun` including its input payload, output payload, timing info, and current status. Useful for polling a run's progress or examining the final result of a completed run.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `agent_id` belongs to company.
3. Fetch `AgentRun` by `run_id` scoped to `agent` + `company`.
4. Return full run detail with nested agent, project, and user info.

### Request JSON

```json
// No request body — agent_id and run_id are path parameters
// GET /api/v1/agents/b2c3d4e5.../runs/r1b2c3d4...
```

### Response JSON

```json
{
  "id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "agent": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Research Agent v2",
    "agent_type": "internal"
  },
  "project_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "topic_id": "t1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "input_payload": {
    "message": "Research the latest advancements in quantum computing...",
    "context": { "language": "en", "max_length": 500 }
  },
  "output_payload": {
    "summary": "Quantum computing has seen three major breakthroughs in 2025...",
    "sources": ["https://example.com/paper1", "https://example.com/paper2"]
  },
  "error": null,
  "started_at": "2026-05-22T09:00:05Z",
  "completed_at": "2026-05-22T09:01:33Z",
  "triggered_by": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "noaman@example.com"
  },
  "created_at": "2026-05-22T09:00:00Z",
  "updated_at": "2026-05-22T09:01:33Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class AgentBriefOut(Schema):
    id: UUID
    name: str
    agent_type: str


class AgentRunDetailOut(Schema):
    id: UUID
    agent: AgentBriefOut
    project_id: UUID
    topic_id: Optional[UUID]
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    triggered_by: Optional[UserBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AgentRun` — primary record
- `AIAgent` — nested brief
- `Project` — FK reference
- `ChatTopic` — optional FK reference
- `User` — `triggered_by` nested
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun
from ninja.errors import HttpError

def get_agent_run(request, agent_id, run_id):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    try:
        return AgentRun.objects.select_related(
            "agent", "triggered_by"
        ).get(
            id=run_id,
            agent=agent,
            company=company,
        )
    except AgentRun.DoesNotExist:
        raise HttpError(404, "Run not found.")
```

---

## 13.11 GET /api/v1/agents/{agent_id}/runs/{run_id}/steps

### Detail

Returns the ordered list of execution steps taken during an `AgentRun`. Each step represents one agent action (e.g. tool call, reasoning, memory read, approval request). This is useful for audit, debugging, and building step-by-step run visualizations in the UI.

> **Note:** `AgentRunStep` is a proposed new model not yet in the schema. See Models Involved section for the proposed structure.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `agent_id` belongs to company.
3. Fetch `AgentRun` by `run_id` scoped to `agent` + `company`.
4. Query `AgentRunStep` ordered by `step_index ASC`.
5. Return ordered list of steps.

### Request JSON

```json
// No request body — path parameters only
// GET /api/v1/agents/{agent_id}/runs/{run_id}/steps
```

### Response JSON

```json
{
  "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total_steps": 4,
  "steps": [
    {
      "id": "s1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "step_index": 1,
      "step_type": "reasoning",
      "title": "Analyzing user request",
      "input": { "message": "Research quantum computing..." },
      "output": { "plan": "1. Search arXiv. 2. Search Google Scholar. 3. Summarize." },
      "status": "completed",
      "tool_name": null,
      "tool_call_id": null,
      "duration_ms": 450,
      "created_at": "2026-05-22T09:00:06Z"
    },
    {
      "id": "s2b2c3d4-e5f6-7890-abcd-ef1234567891",
      "step_index": 2,
      "step_type": "tool_call",
      "title": "Calling web_search",
      "input": { "query": "quantum computing breakthroughs 2025" },
      "output": { "results": ["..."] },
      "status": "completed",
      "tool_name": "web_search",
      "tool_call_id": "call_abc123",
      "duration_ms": 1230,
      "created_at": "2026-05-22T09:00:07Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class AgentRunStepOut(Schema):
    id: UUID
    step_index: int
    step_type: str          # "reasoning" | "tool_call" | "approval" | "memory" | "output"
    title: str
    input: Optional[dict[str, Any]]
    output: Optional[dict[str, Any]]
    status: str             # "pending" | "running" | "completed" | "failed"
    tool_name: Optional[str]
    tool_call_id: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime


class AgentRunStepsOut(Schema):
    run_id: UUID
    total_steps: int
    steps: list[AgentRunStepOut]
```

### Models Involved

- `AgentRunStep` (**proposed** — not yet migrated)
  ```python
  class AgentRunStep(BaseModel):
      run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
      company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="%(class)s_items")
      step_index = models.PositiveIntegerField()
      step_type = models.CharField(max_length=50)   # reasoning, tool_call, approval, memory, output
      title = models.CharField(max_length=255)
      input = models.JSONField(default=dict, blank=True)
      output = models.JSONField(default=dict, blank=True)
      status = models.CharField(max_length=20, default="pending")
      tool_name = models.CharField(max_length=255, null=True, blank=True)
      tool_call_id = models.CharField(max_length=255, null=True, blank=True)
      duration_ms = models.PositiveIntegerField(null=True, blank=True)

      class Meta:
          db_table = "intelligence_agent_run_step"
          ordering = ["step_index"]
          constraints = [
              models.UniqueConstraint(
                  fields=("run", "step_index"),
                  name="uniq_run_step_index",
              )
          ]
  ```
- `AgentRun` — parent run validation
- `AIAgent` — ownership scope
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun, AgentRunStep
from ninja.errors import HttpError

def list_run_steps(request, agent_id, run_id):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    try:
        run = AgentRun.objects.get(id=run_id, agent=agent, company=company)
    except AgentRun.DoesNotExist:
        raise HttpError(404, "Run not found.")

    steps = AgentRunStep.objects.filter(
        run=run,
        company=company,
    ).order_by("step_index")

    return {
        "run_id": run.id,
        "total_steps": steps.count(),
        "steps": list(steps),
    }
```

---

## 13.12 GET /api/v1/agents/{agent_id}/runs/{run_id}/logs

### Detail

Returns raw execution log entries for a specific `AgentRun`. Logs capture low-level events (LLM token streams, tool inputs/outputs, errors, retries) for debugging purposes. Supports optional filtering by log level and step index. This is a developer/admin-facing endpoint intended for troubleshooting.

> **Note:** `AgentRunLog` is a proposed new model. See Models Involved for proposed structure.

### Flow

1. Authenticate request; resolve `current_company`.
2. Validate `agent_id` belongs to company.
3. Fetch `AgentRun` by `run_id` scoped to `agent` + `company`.
4. Query `AgentRunLog` filtered by `run`, optionally by `level` and `step_index`.
5. Return ordered log entries (oldest first).

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/agents/{agent_id}/runs/{run_id}/logs?level=error&step_index=2
{
  "level": "error",       // optional: "debug" | "info" | "warning" | "error"
  "step_index": 2,        // optional: filter logs for a specific step
  "page": 1,
  "page_size": 50
}
```

### Response JSON

```json
{
  "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "l1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "step_index": 2,
      "level": "info",
      "message": "Calling tool: web_search with query='quantum computing breakthroughs 2025'",
      "payload": {
        "tool": "web_search",
        "input": { "query": "quantum computing breakthroughs 2025" }
      },
      "created_at": "2026-05-22T09:00:07Z"
    },
    {
      "id": "l2b2c3d4-e5f6-7890-abcd-ef1234567891",
      "step_index": 2,
      "level": "info",
      "message": "Tool call completed. Received 5 results.",
      "payload": { "result_count": 5 },
      "created_at": "2026-05-22T09:00:08Z"
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema, FilterSchema
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class AgentRunLogFilterSchema(FilterSchema):
    level: Optional[str] = None        # "debug" | "info" | "warning" | "error"
    step_index: Optional[int] = None


class AgentRunLogOut(Schema):
    id: UUID
    step_index: Optional[int]
    level: str
    message: str
    payload: Optional[dict[str, Any]]
    created_at: datetime


class AgentRunLogsOut(Schema):
    run_id: UUID
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[AgentRunLogOut]
```

### Models Involved

- `AgentRunLog` (**proposed** — not yet migrated)
  ```python
  class AgentRunLog(UUIDModel, TimeStampedModel):
      run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="logs")
      company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="%(class)s_items")
      step_index = models.PositiveIntegerField(null=True, blank=True)
      level = models.CharField(
          max_length=10,
          choices=[("debug","Debug"),("info","Info"),("warning","Warning"),("error","Error")],
          default="info",
          db_index=True,
      )
      message = models.TextField()
      payload = models.JSONField(default=dict, blank=True)

      class Meta:
          db_table = "intelligence_agent_run_log"
          ordering = ["created_at"]
          indexes = [
              models.Index(fields=["run", "level"]),
              models.Index(fields=["run", "step_index"]),
          ]
  ```
- `AgentRun` — parent run validation
- `AIAgent` — ownership scope
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import AIAgent, AgentRun, AgentRunLog
from ninja.errors import HttpError

def list_run_logs(request, agent_id, run_id, filters: AgentRunLogFilterSchema):
    company = request.auth.current_company

    try:
        agent = AIAgent.objects.get(id=agent_id, company=company, is_active=True)
    except AIAgent.DoesNotExist:
        raise HttpError(404, "Agent not found.")

    try:
        run = AgentRun.objects.get(id=run_id, agent=agent, company=company)
    except AgentRun.DoesNotExist:
        raise HttpError(404, "Run not found.")

    qs = AgentRunLog.objects.filter(run=run, company=company)

    if filters.level:
        qs = qs.filter(level=filters.level)

    if filters.step_index is not None:
        qs = qs.filter(step_index=filters.step_index)

    return qs.order_by("created_at")
```

---

## Summary: New Models Required

Two new models must be added to the `intelligence` module before implementing the steps and logs endpoints:

| Model | Table | Description |
| --- | --- | --- |
| `AgentRunStep` | `intelligence_agent_run_step` | Ordered execution steps within a run |
| `AgentRunLog` | `intelligence_agent_run_log` | Low-level log lines per run/step |

Both should extend `BaseModel` (for `AgentRunStep`) or `UUIDModel + TimeStampedModel` (for `AgentRunLog`, since logs are append-only and don't need soft-delete). Both require a `company` FK for tenant-level querying.
