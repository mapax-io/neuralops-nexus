# AI Model APIs — Full Documentation

> **Base path:** `/api/v1/models`
> **App:** `nexus-nucleus` → `nucleus` → `intelligence.py`
> **Django Model:** `AIModel` (db_table: `intelligence_ai_model`)
> **Auth:** Bearer token required on all endpoints

---

## Model Reference

```python
class AIModel(TenantBaseModel):
    # Provider choices: litellm | openai | anthropic | ollama | azure | local
    name           = CharField(max_length=255)            # unique per company
    provider       = CharField(max_length=50, choices=Provider.choices)
    model_id       = CharField(max_length=255)            # e.g. "gpt-4o", "claude-sonnet-4"
    created_by     = ForeignKey(User, null=True)
    description    = TextField(null=True, blank=True)
    api_base       = URLField(null=True, blank=True)      # custom endpoint
    secret_ref     = CharField(max_length=255, null=True) # secret manager key
    temperature    = FloatField(default=0.7)
    max_tokens     = PositiveIntegerField(default=4096)
    context_window = PositiveIntegerField(default=8192)
    supports_tools     = BooleanField(default=False)
    supports_streaming = BooleanField(default=True)
    supports_vision    = BooleanField(default=False)
    supports_audio     = BooleanField(default=False)
    config         = JSONField(default=dict)              # provider-specific extras
    # From TenantBaseModel:
    id         = UUIDField(primary_key=True)
    company    = ForeignKey(Company)
    is_active  = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    deleted_at = DateTimeField(null=True)
```

---

## 1. `GET /api/v1/models` — List AI Models

### Detail

Returns all AI models belonging to the authenticated user's active company. Supports filtering by provider and active status. Used by the frontend model selector, agent configuration, and persona creation flows.

### Flow

```
Client → Auth Middleware (validate JWT) → Resolve company from user session
       → Filter AIModel by company + is_active
       → Paginate → Return list
```

### Request

No request body. Query parameters:

| Parameter  | Type    | Required | Description                                      |
|------------|---------|----------|--------------------------------------------------|
| `provider` | string  | No       | Filter by provider (`openai`, `anthropic`, etc.) |
| `is_active`| boolean | No       | Default `true`. Pass `false` to include inactive |
| `page`     | int     | No       | Page number (default: 1)                        |
| `page_size`| int     | No       | Items per page (default: 20, max: 100)          |

### Response JSON

```json
{
  "count": 3,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "id": "b1e2c3d4-0000-0000-0000-000000000001",
      "name": "GPT-4o Production",
      "provider": "openai",
      "model_id": "gpt-4o",
      "description": "Primary model for all customer-facing features.",
      "api_base": null,
      "temperature": 0.7,
      "max_tokens": 4096,
      "context_window": 128000,
      "supports_tools": true,
      "supports_streaming": true,
      "supports_vision": true,
      "supports_audio": false,
      "is_active": true,
      "created_at": "2025-01-10T09:00:00Z",
      "updated_at": "2025-03-01T12:00:00Z"
    }
  ]
}
```

> **Note:** `secret_ref` and `config` are **never** returned in list responses for security reasons.

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional

class AIModelListItem(Schema):
    id: UUID
    name: str
    provider: str
    model_id: str
    description: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float
    max_tokens: int
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_audio: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

class AIModelListResponse(Schema):
    count: int
    page: int
    page_size: int
    results: list[AIModelListItem]

class AIModelListFilters(Schema):
    provider: Optional[str] = None
    is_active: Optional[bool] = True
    page: int = 1
    page_size: int = 20
```

### Models Involved

- `AIModel` — primary
- `Company` — tenant scoping via `TenantBaseModel`
- `Human` / `User` — resolved from JWT for company context

### Django ORM Query (Proposed)

```python
from nucleus.models import AIModel

def list_models(company_id, provider=None, is_active=True, page=1, page_size=20):
    qs = AIModel.objects.filter(
        company_id=company_id,
        is_active=is_active,
        deleted_at__isnull=True,
    ).select_related("created_by").order_by("-created_at")

    if provider:
        qs = qs.filter(provider=provider)

    offset = (page - 1) * page_size
    return qs.count(), qs[offset: offset + page_size]
```

---

## 2. `POST /api/v1/models` — Create AI Model

### Detail

Creates a new AI model configuration for the authenticated user's company. The `secret_ref` field should reference a secret manager key (e.g., Vault, AWS SSM) — **never store raw API keys**. The `name` must be unique within the company.

### Flow

```
Client → Auth Middleware → Resolve company
       → Validate payload (unique name per company)
       → Create AIModel record
       → Return created model (without secret_ref)
```

### Request JSON

```json
{
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "model_id": "claude-sonnet-4-20250514",
  "description": "Used for staging and QA testing.",
  "api_base": null,
  "secret_ref": "secrets/anthropic/staging-key",
  "temperature": 0.5,
  "max_tokens": 8192,
  "context_window": 200000,
  "supports_tools": true,
  "supports_streaming": true,
  "supports_vision": true,
  "supports_audio": false,
  "config": {
    "thinking_mode": false,
    "extra_headers": {}
  }
}
```

### Response JSON

`HTTP 201 Created`

```json
{
  "id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "model_id": "claude-sonnet-4-20250514",
  "description": "Used for staging and QA testing.",
  "api_base": null,
  "temperature": 0.5,
  "max_tokens": 8192,
  "context_window": 200000,
  "supports_tools": true,
  "supports_streaming": true,
  "supports_vision": true,
  "supports_audio": false,
  "is_active": true,
  "created_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

class AIModelCreateIn(Schema):
    name: str
    provider: str                         # litellm | openai | anthropic | ollama | azure | local
    model_id: str
    description: Optional[str] = None
    api_base: Optional[str] = None
    secret_ref: Optional[str] = None      # secret manager reference only
    temperature: float = 0.7
    max_tokens: int = 4096
    context_window: int = 8192
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    config: dict[str, Any] = {}

class AIModelCreateOut(Schema):
    id: UUID
    name: str
    provider: str
    model_id: str
    description: Optional[str]
    api_base: Optional[str]
    temperature: float
    max_tokens: int
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_audio: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AIModel` — created
- `Company` — FK from tenant context
- `User` — stored in `created_by`

### Django ORM Query (Proposed)

```python
from nucleus.models import AIModel

def create_model(company_id, user_id, data: dict) -> AIModel:
    # Uniqueness is enforced by DB constraint: uniq_ai_model_name_per_company
    model = AIModel.objects.create(
        company_id=company_id,
        created_by_id=user_id,
        name=data["name"],
        provider=data["provider"],
        model_id=data["model_id"],
        description=data.get("description"),
        api_base=data.get("api_base"),
        secret_ref=data.get("secret_ref"),
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 4096),
        context_window=data.get("context_window", 8192),
        supports_tools=data.get("supports_tools", False),
        supports_streaming=data.get("supports_streaming", True),
        supports_vision=data.get("supports_vision", False),
        supports_audio=data.get("supports_audio", False),
        config=data.get("config", {}),
    )
    return model
```

---

## 3. `GET /api/v1/models/{model_id}` — Get AI Model Detail

### Detail

Retrieves the full configuration of a single AI model by its UUID. Requires the model to belong to the authenticated user's company. Returns more fields than the list endpoint (e.g., `config`) but **not** `secret_ref`.

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id
       → 404 if not found or belongs to a different company
       → Return model detail
```

### Request

No request body. `model_id` is a UUID path parameter.

### Response JSON

`HTTP 200 OK`

```json
{
  "id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "model_id": "claude-sonnet-4-20250514",
  "description": "Used for staging and QA testing.",
  "api_base": null,
  "temperature": 0.5,
  "max_tokens": 8192,
  "context_window": 200000,
  "supports_tools": true,
  "supports_streaming": true,
  "supports_vision": true,
  "supports_audio": false,
  "config": {
    "thinking_mode": false,
    "extra_headers": {}
  },
  "is_active": true,
  "created_by": {
    "id": "user-uuid-here",
    "full_name": "Alice Smith",
    "email": "alice@acme.com"
  },
  "created_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T10:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

class CreatedByOut(Schema):
    id: UUID
    full_name: str
    email: str

class AIModelDetailOut(Schema):
    id: UUID
    name: str
    provider: str
    model_id: str
    description: Optional[str]
    api_base: Optional[str]
    temperature: float
    max_tokens: int
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_audio: bool
    config: dict[str, Any]
    is_active: bool
    created_by: Optional[CreatedByOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `AIModel` — primary
- `Company` — scoping
- `Human` / `User` — joined for `created_by`

### Django ORM Query (Proposed)

```python
from nucleus.models import AIModel
from django.shortcuts import get_object_or_404

def get_model_detail(company_id, model_id) -> AIModel:
    return get_object_or_404(
        AIModel.objects.select_related("created_by__human_profile"),
        id=model_id,
        company_id=company_id,
        deleted_at__isnull=True,
    )
```

---

## 4. `PATCH /api/v1/models/{model_id}` — Update AI Model

### Detail

Partially updates an existing AI model. All fields are optional — only fields present in the request body are updated. The `name` uniqueness constraint per company is enforced. `model_id` (the provider identifier) and `provider` can be changed, but doing so may break existing agents or personas referencing this model.

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id (404 if missing)
       → Validate patch payload
       → Apply partial update
       → Return updated model
```

### Request JSON

```json
{
  "temperature": 0.3,
  "max_tokens": 16384,
  "description": "Updated: now used for production too.",
  "supports_vision": true,
  "config": {
    "thinking_mode": true
  }
}
```

### Response JSON

`HTTP 200 OK`

```json
{
  "id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "model_id": "claude-sonnet-4-20250514",
  "description": "Updated: now used for production too.",
  "api_base": null,
  "temperature": 0.3,
  "max_tokens": 16384,
  "context_window": 200000,
  "supports_tools": true,
  "supports_streaming": true,
  "supports_vision": true,
  "supports_audio": false,
  "config": {
    "thinking_mode": true
  },
  "is_active": true,
  "created_at": "2026-05-22T10:00:00Z",
  "updated_at": "2026-05-22T11:30:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional, Any

class AIModelPatchIn(Schema):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    description: Optional[str] = None
    api_base: Optional[str] = None
    secret_ref: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    context_window: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_audio: Optional[bool] = None
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
```

### Models Involved

- `AIModel` — updated
- `Company` — scoping constraint
- `AIAgent` — may be impacted (read-only concern, not cascade)
- `Persona` — may be impacted (read-only concern, not cascade)

### Django ORM Query (Proposed)

```python
from nucleus.models import AIModel
from django.shortcuts import get_object_or_404

def patch_model(company_id, model_id, data: dict) -> AIModel:
    instance = get_object_or_404(
        AIModel,
        id=model_id,
        company_id=company_id,
        deleted_at__isnull=True,
    )
    updatable_fields = [
        "name", "provider", "model_id", "description", "api_base",
        "secret_ref", "temperature", "max_tokens", "context_window",
        "supports_tools", "supports_streaming", "supports_vision",
        "supports_audio", "config", "is_active",
    ]
    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(instance, field, data[field])

    instance.save()
    return instance
```

---

## 5. `DELETE /api/v1/models/{model_id}` — Delete AI Model

### Detail

Soft-deletes an AI model by setting `deleted_at` to the current timestamp and `is_active` to `False`. Hard delete is not performed at the API layer to preserve audit integrity. Returns `HTTP 204 No Content`. Will return `HTTP 409 Conflict` if any active `AIAgent` or `Persona` is still referencing this model (FK with `PROTECT`).

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id (404 if missing)
       → Check for dependents (AIAgent, Persona) → 409 if any active
       → Soft-delete: set deleted_at=now(), is_active=False
       → Return 204
```

### Request

No request body. `model_id` is a UUID path parameter.

### Response JSON

`HTTP 204 No Content` (empty body on success)

`HTTP 409 Conflict` (if dependents exist):

```json
{
  "detail": "Cannot delete model. It is referenced by 2 active agent(s): ['ResearchBot', 'SupportAgent']."
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema

class DeleteConflictOut(Schema):
    detail: str
```

### Models Involved

- `AIModel` — soft-deleted
- `AIAgent` — checked for active references (`PROTECT` constraint)
- `Persona` — checked for active references (`PROTECT` constraint)

### Django ORM Query (Proposed)

```python
from nucleus.models import AIModel, AIAgent, Persona
from django.utils import timezone
from django.shortcuts import get_object_or_404

def delete_model(company_id, model_id):
    instance = get_object_or_404(
        AIModel,
        id=model_id,
        company_id=company_id,
        deleted_at__isnull=True,
    )

    # Check for active dependents
    blocking_agents = list(
        AIAgent.objects.filter(
            model=instance,
            is_active=True,
            deleted_at__isnull=True,
        ).values_list("name", flat=True)
    )
    if blocking_agents:
        raise ConflictError(f"Referenced by agents: {blocking_agents}")

    # Soft delete
    instance.deleted_at = timezone.now()
    instance.is_active = False
    instance.save(update_fields=["deleted_at", "is_active", "updated_at"])
```

---

## 6. `POST /api/v1/models/{model_id}/test` — Test AI Model

### Detail

Sends a minimal test prompt to the configured AI model using the stored credentials and runtime settings. Verifies connectivity, authentication, and basic inference. Returns the model's raw response and latency. Does **not** create any `ChatMessage` or `ModelUsageLog` records — this is a diagnostic endpoint only.

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id
       → Retrieve credentials via secret_ref
       → Call LiteLLM / provider with test prompt
       → Return response text + latency_ms
       → On failure: return 502 with error detail
```

### Request JSON

```json
{
  "prompt": "Say 'OK' if you can hear me.",
  "max_tokens": 10
}
```

All fields are optional — defaults are used if omitted.

### Response JSON

`HTTP 200 OK`

```json
{
  "success": true,
  "response": "OK",
  "latency_ms": 312,
  "model_used": "claude-sonnet-4-20250514",
  "provider": "anthropic",
  "tokens": {
    "prompt": 14,
    "completion": 3,
    "total": 17
  }
}
```

`HTTP 502 Bad Gateway` (provider unreachable or auth failure):

```json
{
  "success": false,
  "error": "AuthenticationError: Invalid API key provided.",
  "latency_ms": 98
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional

class AIModelTestIn(Schema):
    prompt: str = "Respond with 'OK' only."
    max_tokens: int = 10

class TokenUsage(Schema):
    prompt: int
    completion: int
    total: int

class AIModelTestOut(Schema):
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    latency_ms: int
    model_used: Optional[str] = None
    provider: Optional[str] = None
    tokens: Optional[TokenUsage] = None
```

### Models Involved

- `AIModel` — config source
- `ModelUsageLog` — **not** written (diagnostic only)
- `Company` — scoping

### Django ORM Query (Proposed)

```python
import time
import litellm
from nucleus.models import AIModel
from django.shortcuts import get_object_or_404

def test_model(company_id, model_id, prompt: str, max_tokens: int = 10):
    instance = get_object_or_404(
        AIModel,
        id=model_id,
        company_id=company_id,
        deleted_at__isnull=True,
        is_active=True,
    )

    # Resolve secret (implementation depends on secret backend)
    api_key = resolve_secret(instance.secret_ref)

    start = time.time()
    try:
        response = litellm.completion(
            model=instance.model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=instance.temperature,
            api_base=instance.api_base,
            api_key=api_key,
        )
        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": True,
            "response": response.choices[0].message.content,
            "latency_ms": latency_ms,
            "model_used": instance.model_id,
            "provider": instance.provider,
            "tokens": {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens,
            },
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return {"success": False, "error": str(e), "latency_ms": latency_ms}
```

---

## 7. `GET /api/v1/models/{model_id}/health` — AI Model Health Check

### Detail

Performs a lightweight liveness probe against the model's provider endpoint. Unlike `/test`, this does **not** send any prompt to the model. It only verifies that the provider API is reachable and that the model identifier is resolvable (e.g., via a models list call or HEAD request). Intended for dashboards and monitoring integrations.

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id
       → Ping provider endpoint (no inference call)
       → Return health status + response_time_ms
```

### Request

No request body.

### Response JSON

`HTTP 200 OK`

```json
{
  "model_id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "status": "healthy",
  "response_time_ms": 145,
  "checked_at": "2026-05-22T11:00:00Z",
  "details": {
    "endpoint_reachable": true,
    "model_exists": true
  }
}
```

`HTTP 200 OK` (degraded):

```json
{
  "model_id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "provider": "anthropic",
  "status": "unhealthy",
  "response_time_ms": 5001,
  "checked_at": "2026-05-22T11:00:00Z",
  "details": {
    "endpoint_reachable": false,
    "model_exists": false,
    "error": "Connection timed out"
  }
}
```

> **Note:** Always returns `HTTP 200` — the `status` field carries the health state. Never returns `502` so monitoring tools can always parse the payload.

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID
from datetime import datetime
from typing import Optional, Any

class HealthDetails(Schema):
    endpoint_reachable: bool
    model_exists: bool
    error: Optional[str] = None

class AIModelHealthOut(Schema):
    model_id: UUID
    name: str
    provider: str
    status: str                       # "healthy" | "unhealthy" | "degraded"
    response_time_ms: int
    checked_at: datetime
    details: HealthDetails
```

### Models Involved

- `AIModel` — config source
- `Company` — scoping
- No writes performed

### Django ORM Query (Proposed)

```python
import time
import httpx
from nucleus.models import AIModel
from django.utils import timezone
from django.shortcuts import get_object_or_404

PROVIDER_HEALTH_URLS = {
    "openai":    "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "ollama":    "{api_base}/api/tags",
}

def check_model_health(company_id, model_id):
    instance = get_object_or_404(
        AIModel,
        id=model_id,
        company_id=company_id,
        deleted_at__isnull=True,
    )

    api_key = resolve_secret(instance.secret_ref)
    base_url = instance.api_base or PROVIDER_HEALTH_URLS.get(instance.provider, "")

    start = time.time()
    try:
        resp = httpx.get(base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
        response_time_ms = int((time.time() - start) * 1000)
        reachable = resp.status_code < 500
        return {
            "model_id": instance.id,
            "name": instance.name,
            "provider": instance.provider,
            "status": "healthy" if reachable else "unhealthy",
            "response_time_ms": response_time_ms,
            "checked_at": timezone.now(),
            "details": {"endpoint_reachable": reachable, "model_exists": reachable},
        }
    except Exception as e:
        response_time_ms = int((time.time() - start) * 1000)
        return {
            "model_id": instance.id,
            "name": instance.name,
            "provider": instance.provider,
            "status": "unhealthy",
            "response_time_ms": response_time_ms,
            "checked_at": timezone.now(),
            "details": {"endpoint_reachable": False, "model_exists": False, "error": str(e)},
        }
```

---

## 8. `GET /api/v1/models/{model_id}/usage` — AI Model Usage Stats

### Detail

Returns aggregated usage statistics for a specific AI model scoped to the authenticated user's company. Data is sourced from `ModelUsageLog`. Supports date range filtering and optional grouping by day or user. Intended for billing dashboards, cost analysis, and capacity planning.

### Flow

```
Client → Auth Middleware → Resolve company
       → Fetch AIModel by model_id + company_id (404 if missing)
       → Query ModelUsageLog filtered by model + company + date range
       → Aggregate: SUM tokens, SUM cost, AVG latency, COUNT requests
       → Return aggregated stats + optional breakdown
```

### Request

No request body. Query parameters:

| Parameter    | Type   | Required | Description                                 |
|--------------|--------|----------|---------------------------------------------|
| `from_date`  | string | No       | ISO 8601 date. Default: 30 days ago        |
| `to_date`    | string | No       | ISO 8601 date. Default: today              |
| `group_by`   | string | No       | `day` or `user`. Default: no grouping      |

### Response JSON

`HTTP 200 OK` (no grouping):

```json
{
  "model_id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "period": {
    "from": "2026-04-22",
    "to": "2026-05-22"
  },
  "summary": {
    "total_requests": 1842,
    "total_prompt_tokens": 4812300,
    "total_completion_tokens": 982100,
    "total_tokens": 5794400,
    "total_cost_usd": "12.847600",
    "avg_latency_ms": 410
  }
}
```

`HTTP 200 OK` (`group_by=day`):

```json
{
  "model_id": "c2f3a4b5-0000-0000-0000-000000000002",
  "name": "Claude Sonnet Staging",
  "period": {
    "from": "2026-05-20",
    "to": "2026-05-22"
  },
  "summary": {
    "total_requests": 120,
    "total_tokens": 340000,
    "total_cost_usd": "0.712400",
    "avg_latency_ms": 385
  },
  "breakdown": [
    {
      "date": "2026-05-20",
      "requests": 38,
      "total_tokens": 104000,
      "cost_usd": "0.218100",
      "avg_latency_ms": 370
    },
    {
      "date": "2026-05-21",
      "requests": 45,
      "total_tokens": 128000,
      "cost_usd": "0.268300",
      "avg_latency_ms": 400
    },
    {
      "date": "2026-05-22",
      "requests": 37,
      "total_tokens": 108000,
      "cost_usd": "0.226000",
      "avg_latency_ms": 385
    }
  ]
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from uuid import UUID
from datetime import date
from typing import Optional
from decimal import Decimal

class UsagePeriod(Schema):
    from_date: date
    to_date: date

class UsageSummary(Schema):
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: Decimal
    avg_latency_ms: int

class UsageBreakdownItem(Schema):
    date: date
    requests: int
    total_tokens: int
    cost_usd: Decimal
    avg_latency_ms: int

class AIModelUsageOut(Schema):
    model_id: UUID
    name: str
    period: UsagePeriod
    summary: UsageSummary
    breakdown: Optional[list[UsageBreakdownItem]] = None

class AIModelUsageFilters(Schema):
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    group_by: Optional[str] = None    # "day" | "user"
```

### Models Involved

- `AIModel` — config source / FK filter
- `ModelUsageLog` — primary data source (aggregated)
- `Company` — scoping
- `User` — optional grouping dimension

### Django ORM Query (Proposed)

```python
from django.db.models import Sum, Avg, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from nucleus.models import AIModel, ModelUsageLog

def get_model_usage(company_id, model_id, from_date=None, to_date=None, group_by=None):
    if not from_date:
        from_date = (timezone.now() - timedelta(days=30)).date()
    if not to_date:
        to_date = timezone.now().date()

    base_qs = ModelUsageLog.objects.filter(
        company_id=company_id,
        model_id=model_id,
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )

    summary = base_qs.aggregate(
        total_requests=Count("id"),
        total_prompt_tokens=Sum("prompt_tokens"),
        total_completion_tokens=Sum("completion_tokens"),
        total_tokens=Sum("total_tokens"),
        total_cost_usd=Sum("cost_usd"),
        avg_latency_ms=Avg("latency_ms"),
    )

    breakdown = None
    if group_by == "day":
        breakdown = list(
            base_qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                requests=Count("id"),
                total_tokens=Sum("total_tokens"),
                cost_usd=Sum("cost_usd"),
                avg_latency_ms=Avg("latency_ms"),
            )
            .order_by("date")
        )

    return summary, breakdown
```

---

## Summary Table

| # | Method | Endpoint | Auth | DB Write | Description |
|---|--------|----------|------|----------|-------------|
| 1 | GET    | `/api/v1/models` | ✅ | ❌ | List all models for company |
| 2 | POST   | `/api/v1/models` | ✅ | ✅ | Create new AI model |
| 3 | GET    | `/api/v1/models/{model_id}` | ✅ | ❌ | Get single model detail |
| 4 | PATCH  | `/api/v1/models/{model_id}` | ✅ | ✅ | Partially update model |
| 5 | DELETE | `/api/v1/models/{model_id}` | ✅ | ✅ | Soft-delete model |
| 6 | POST   | `/api/v1/models/{model_id}/test` | ✅ | ❌ | Live inference test |
| 7 | GET    | `/api/v1/models/{model_id}/health` | ✅ | ❌ | Provider health probe |
| 8 | GET    | `/api/v1/models/{model_id}/usage` | ✅ | ❌ | Aggregated usage stats |

---

## Models Dependency Map

```
AIModel
  ├── TenantBaseModel (company FK, is_active, deleted_at, UUID PK)
  ├── created_by → User
  ├── ← AIAgent.model (PROTECT — blocks delete if active)
  ├── ← Persona.model (PROTECT — blocks delete if active)
  └── ← ModelUsageLog.model (SET_NULL — usage history preserved)
```

---

*Generated for nexus-nucleus · intelligence.py · May 2026*
