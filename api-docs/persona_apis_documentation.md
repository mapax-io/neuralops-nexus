# 14. Persona APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/personas |
| POST | /api/v1/personas |
| GET | /api/v1/personas/{persona_id} |
| PATCH | /api/v1/personas/{persona_id} |
| DELETE | /api/v1/personas/{persona_id} |
| POST | /api/v1/personas/{persona_id}/clone |

---

## Background: What is a Persona?

A **Persona** is a named AI identity that users interact with inside chat topics. It wraps either an `AIModel` (a raw LLM) or an `AIAgent` (a tool-capable agent) with a human-facing identity — name, avatar, tone, style, and system instructions. Each Persona is backed by a `User` record of `user_type=persona` (`identity_user`) so it can participate in conversations just like a human member.

**Source types:**
- `model` — backed directly by an `AIModel` (pure LLM, no tools)
- `agent` — backed by an `AIAgent` (can use tools, run multi-step tasks)

**Key DB constraint:** `persona_model_or_agent_required` enforces that `source_type=model` always has a `model` FK and `source_type=agent` always has an `agent` FK.

> **Proposed additions (from api4.md):** `tone`, `style`, `behavior`, and `system_instructions` fields are not yet in the migration. Their proposed model definitions are documented in the relevant sections below.

---

## 14.1 GET /api/v1/personas

### Detail

Returns a paginated list of all Personas belonging to the authenticated user's active company. Supports optional filtering by `source_type` (model or agent) and active status. Excludes soft-deleted records. Returns summary-level data suitable for listing in a UI sidebar or picker.

### Flow

1. Authenticate request via JWT; resolve `current_company` from user.
2. Query `Persona` filtered by `company` and `is_active=True`.
3. Apply optional query filters (`source_type`, `search`).
4. `select_related` on `model`, `agent`, `identity_user`, `created_by`.
5. Return paginated list ordered by `name ASC`.

### Request JSON

```json
// Query Parameters (no request body)
// GET /api/v1/personas?source_type=agent&search=support&page=1&page_size=20
{
  "source_type": "agent",   // optional: "model" | "agent"
  "search": "support",      // optional: name search
  "page": 1,
  "page_size": 20
}
```

### Response JSON

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "pe1b2c3d-e5f6-7890-abcd-ef1234567890",
      "name": "Aria",
      "description": "Friendly support persona for customer-facing interactions",
      "source_type": "agent",
      "avatar_url": "https://cdn.example.com/avatars/aria.png",
      "is_active": true,
      "model": null,
      "agent": {
        "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "name": "Support Agent",
        "agent_type": "internal"
      },
      "identity_user": {
        "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "username": "aria_persona"
      },
      "created_by": {
        "id": "u2b2c3d4-e5f6-7890-abcd-ef1234567891",
        "username": "noaman@example.com"
      },
      "created_at": "2026-05-01T10:00:00Z",
      "updated_at": "2026-05-15T14:30:00Z"
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


class AIAgentBriefOut(Schema):
    id: UUID
    name: str
    agent_type: str


class UserBriefOut(Schema):
    id: UUID
    username: str


class PersonaListItemOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    source_type: str
    avatar_url: Optional[str]
    is_active: bool
    model: Optional[AIModelBriefOut]
    agent: Optional[AIAgentBriefOut]
    identity_user: UserBriefOut
    created_by: Optional[UserBriefOut]
    created_at: datetime
    updated_at: datetime


class PersonaListOut(Schema):
    count: int
    next: Optional[str]
    previous: Optional[str]
    results: list[PersonaListItemOut]


class PersonaFilterSchema(Schema):
    source_type: Optional[str] = None
    search: Optional[str] = None
```

### Models Involved

- `Persona` — primary listing model
- `AIModel` — FK `model` (nested brief, nullable)
- `AIAgent` — FK `agent` (nested brief, nullable)
- `User` — `identity_user` (nested brief) and `created_by` (nested brief)
- `Company` — tenant scope filter

### Django ORM Query (Proposed)

```python
from nucleus.models import Persona

def list_personas(request, filters):
    qs = Persona.objects.filter(
        company=request.auth.current_company,
        is_active=True,
    ).select_related(
        "model", "agent", "identity_user", "created_by"
    )

    if filters.source_type:
        qs = qs.filter(source_type=filters.source_type)

    if filters.search:
        qs = qs.filter(name__icontains=filters.search)

    return qs.order_by("name")
```

---

## 14.2 POST /api/v1/personas

### Detail

Creates a new Persona in the authenticated user's active company. Requires a `name`, `source_type`, and either a `model_id` (for `source_type=model`) or an `agent_id` (for `source_type=agent`). Automatically creates a backing `User` record with `user_type=persona` to serve as the persona's identity in chat threads. The creating user is recorded as `created_by`.

> **Note:** `tone`, `style`, `behavior`, and `system_instructions` are proposed fields not yet in the migration. They are included here as forward-looking additions per the api4.md adjustment plan.

### Flow

1. Authenticate request; resolve `current_company` and `created_by` user.
2. Validate `source_type` + FK combination (model XOR agent).
3. Validate the provided `model_id` or `agent_id` belongs to same company.
4. Create a backing `User` record: `user_type=persona`, `username=<slugified name>_persona`.
5. Create the `Persona` record linking to the new identity user.
6. Return the full persona detail.

### Request JSON

```json
{
  "name": "Aria",
  "description": "Friendly support persona for customer-facing interactions",
  "source_type": "agent",
  "agent_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "model_id": null,
  "tone": "friendly",
  "style": "concise",
  "behavior": "proactive",
  "system_instructions": "Always greet users by name. Keep responses under 3 sentences unless asked for detail."
}
```

### Response JSON

```json
{
  "id": "pe1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Aria",
  "description": "Friendly support persona for customer-facing interactions",
  "source_type": "agent",
  "avatar_url": null,
  "tone": "friendly",
  "style": "concise",
  "behavior": "proactive",
  "system_instructions": "Always greet users by name. Keep responses under 3 sentences unless asked for detail.",
  "is_active": true,
  "model": null,
  "agent": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Support Agent",
    "agent_type": "internal"
  },
  "identity_user": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "aria_persona"
  },
  "created_by": {
    "id": "u2b2c3d4-e5f6-7890-abcd-ef1234567891",
    "username": "noaman@example.com"
  },
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


class PersonaCreateIn(Schema):
    name: str
    description: Optional[str] = None
    source_type: str                        # "model" | "agent"
    model_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    tone: Optional[str] = None              # proposed: "friendly" | "formal" | "casual" | "technical"
    style: Optional[str] = None             # proposed: "concise" | "verbose" | "bullet-points"
    behavior: Optional[str] = None          # proposed: "proactive" | "reactive" | "guided"
    system_instructions: Optional[str] = None  # proposed


class PersonaDetailOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    source_type: str
    avatar_url: Optional[str]
    tone: Optional[str]
    style: Optional[str]
    behavior: Optional[str]
    system_instructions: Optional[str]
    is_active: bool
    model: Optional[AIModelBriefOut]
    agent: Optional[AIAgentBriefOut]
    identity_user: UserBriefOut
    created_by: Optional[UserBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `Persona` — created record
- `User` — auto-created `identity_user` with `user_type=persona`
- `AIModel` — FK validated (if `source_type=model`)
- `AIAgent` — FK validated (if `source_type=agent`)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils.text import slugify
from nucleus.models import Persona, AIModel, AIAgent
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

User = get_user_model()


@transaction.atomic
def create_persona(request, payload: PersonaCreateIn):
    company = request.auth.current_company
    created_by = request.auth

    # Validate source_type + FK combination
    if payload.source_type == "model" and not payload.model_id:
        raise HttpError(422, "source_type='model' requires model_id.")
    if payload.source_type == "agent" and not payload.agent_id:
        raise HttpError(422, "source_type='agent' requires agent_id.")

    model = None
    if payload.model_id:
        try:
            model = AIModel.objects.get(id=payload.model_id, company=company, is_active=True)
        except AIModel.DoesNotExist:
            raise HttpError(404, "AI Model not found.")

    agent = None
    if payload.agent_id:
        try:
            agent = AIAgent.objects.get(id=payload.agent_id, company=company, is_active=True)
        except AIAgent.DoesNotExist:
            raise HttpError(404, "AI Agent not found.")

    # Create backing identity user
    base_username = f"{slugify(payload.name)}_persona"
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{counter}"
        counter += 1

    identity_user = User.objects.create(
        username=username,
        email=f"{username}@persona.internal",
        user_type=User.UserType.PERSONA,
        is_active=True,
        current_company=company,
    )

    persona = Persona.objects.create(
        company=company,
        name=payload.name,
        description=payload.description,
        source_type=payload.source_type,
        model=model,
        agent=agent,
        identity_user=identity_user,
        created_by=created_by,
        # proposed fields — add after migration:
        # tone=payload.tone,
        # style=payload.style,
        # behavior=payload.behavior,
        # system_instructions=payload.system_instructions,
    )

    return persona
```

---

## 14.3 GET /api/v1/personas/{persona_id}

### Detail

Retrieves the full detail of a single Persona by its UUID. The persona must belong to the authenticated user's active company. Returns all configuration fields including nested model/agent detail, identity user, and the proposed tone/style/behavior/system_instructions fields.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `Persona` by `persona_id` scoped to `company` and `is_active=True`.
3. Return 404 if not found or soft-deleted.
4. Return full persona detail with all nested relations.

### Request JSON

```json
// No request body — persona_id is a path parameter
// GET /api/v1/personas/pe1b2c3d-e5f6-7890-abcd-ef1234567890
```

### Response JSON

```json
{
  "id": "pe1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Aria",
  "description": "Friendly support persona for customer-facing interactions",
  "source_type": "agent",
  "avatar_url": "https://cdn.example.com/avatars/aria.png",
  "tone": "friendly",
  "style": "concise",
  "behavior": "proactive",
  "system_instructions": "Always greet users by name. Keep responses under 3 sentences unless asked for detail.",
  "is_active": true,
  "model": null,
  "agent": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Support Agent",
    "agent_type": "internal",
    "max_steps": 10,
    "allow_parallel_tools": true
  },
  "identity_user": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "aria_persona"
  },
  "created_by": {
    "id": "u2b2c3d4-e5f6-7890-abcd-ef1234567891",
    "username": "noaman@example.com"
  },
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


class AIAgentDetailOut(Schema):
    id: UUID
    name: str
    agent_type: str
    max_steps: int
    allow_parallel_tools: bool


class AIModelFullBriefOut(Schema):
    id: UUID
    name: str
    provider: str
    model_id: str
    supports_tools: bool
    supports_streaming: bool


class PersonaDetailOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    source_type: str
    avatar_url: Optional[str]
    tone: Optional[str]
    style: Optional[str]
    behavior: Optional[str]
    system_instructions: Optional[str]
    is_active: bool
    model: Optional[AIModelFullBriefOut]
    agent: Optional[AIAgentDetailOut]
    identity_user: UserBriefOut
    created_by: Optional[UserBriefOut]
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `Persona` — primary record
- `AIModel` — FK `model` (nested detail, nullable)
- `AIAgent` — FK `agent` (nested detail, nullable)
- `User` — `identity_user` and `created_by` (nested brief)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from nucleus.models import Persona
from ninja.errors import HttpError


def get_persona(request, persona_id):
    try:
        return Persona.objects.select_related(
            "model", "agent", "identity_user", "created_by"
        ).get(
            id=persona_id,
            company=request.auth.current_company,
            is_active=True,
        )
    except Persona.DoesNotExist:
        raise HttpError(404, "Persona not found.")
```

---

## 14.4 PATCH /api/v1/personas/{persona_id}

### Detail

Partially updates an existing Persona. Only fields present in the request body are updated. Allows updating persona identity fields (name, description, avatar), behavioral fields (tone, style, behavior, system_instructions), and the backing model or agent. Changing `source_type` is not permitted via PATCH — clone and recreate instead. The `identity_user` is automatically renamed if `name` changes.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `Persona` by `persona_id` scoped to `company`.
3. Reject any attempt to change `source_type`.
4. If `model_id` or `agent_id` is changed, validate the new FK belongs to same company.
5. If `name` changes, update `identity_user.username` to match new slugified name.
6. Apply provided fields and save.
7. Return updated persona detail.

### Request JSON

```json
{
  "name": "Aria v2",
  "tone": "formal",
  "system_instructions": "Always greet users by name. Provide detailed explanations unless asked to be brief.",
  "max_steps_override": null
}
```

### Response JSON

```json
{
  "id": "pe1b2c3d-e5f6-7890-abcd-ef1234567890",
  "name": "Aria v2",
  "description": "Friendly support persona for customer-facing interactions",
  "source_type": "agent",
  "avatar_url": "https://cdn.example.com/avatars/aria.png",
  "tone": "formal",
  "style": "concise",
  "behavior": "proactive",
  "system_instructions": "Always greet users by name. Provide detailed explanations unless asked to be brief.",
  "is_active": true,
  "model": null,
  "agent": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Support Agent",
    "agent_type": "internal",
    "max_steps": 10,
    "allow_parallel_tools": true
  },
  "identity_user": {
    "id": "u1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "username": "aria_v2_persona"
  },
  "created_by": {
    "id": "u2b2c3d4-e5f6-7890-abcd-ef1234567891",
    "username": "noaman@example.com"
  },
  "created_at": "2026-05-22T08:00:00Z",
  "updated_at": "2026-05-22T10:15:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID


class PersonaUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    model_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    tone: Optional[str] = None
    style: Optional[str] = None
    behavior: Optional[str] = None
    system_instructions: Optional[str] = None
    is_active: Optional[bool] = None
```

### Models Involved

- `Persona` — updated record
- `User` — `identity_user` username sync if name changes
- `AIModel` — optional re-assignment validation
- `AIAgent` — optional re-assignment validation
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils.text import slugify
from nucleus.models import Persona, AIModel, AIAgent
from ninja.errors import HttpError


@transaction.atomic
def update_persona(request, persona_id, payload: PersonaUpdateIn):
    company = request.auth.current_company

    try:
        persona = Persona.objects.select_related("identity_user").get(
            id=persona_id,
            company=company,
            is_active=True,
        )
    except Persona.DoesNotExist:
        raise HttpError(404, "Persona not found.")

    update_fields = []

    for field in ["name", "description", "tone", "style", "behavior",
                  "system_instructions", "is_active"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(persona, field, value)
            update_fields.append(field)

    # Sync identity_user.username if name changed
    if payload.name and persona.identity_user:
        new_username = f"{slugify(payload.name)}_persona"
        persona.identity_user.username = new_username
        persona.identity_user.save(update_fields=["username"])

    if payload.model_id is not None:
        persona.model = AIModel.objects.get(id=payload.model_id, company=company, is_active=True)
        update_fields.append("model")

    if payload.agent_id is not None:
        persona.agent = AIAgent.objects.get(id=payload.agent_id, company=company, is_active=True)
        update_fields.append("agent")

    if update_fields:
        persona.save(update_fields=update_fields + ["updated_at"])

    return persona
```

---

## 14.5 DELETE /api/v1/personas/{persona_id}

### Detail

Soft-deletes a Persona by setting `is_active=False` and recording `deleted_at`. The persona must belong to the authenticated user's active company. The backing `identity_user` is also deactivated (`is_active=False`) to prevent the persona from participating in new chat threads. Existing messages sent by this persona in chat topics are preserved.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch `Persona` by `persona_id` scoped to `company`.
3. Soft-delete the `Persona` record.
4. Deactivate the backing `identity_user` (`User.is_active = False`).
5. Return 204 No Content.

### Request JSON

```json
// No request body — persona_id is a path parameter
// DELETE /api/v1/personas/pe1b2c3d-e5f6-7890-abcd-ef1234567890
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

- `Persona` — soft-deleted record
- `User` — backing `identity_user` deactivated
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from nucleus.models import Persona
from ninja.errors import HttpError


@transaction.atomic
def delete_persona(request, persona_id):
    company = request.auth.current_company

    try:
        persona = Persona.objects.select_related("identity_user").get(
            id=persona_id,
            company=company,
            is_active=True,
        )
    except Persona.DoesNotExist:
        raise HttpError(404, "Persona not found.")

    # Deactivate the backing identity user
    if persona.identity_user:
        persona.identity_user.is_active = False
        persona.identity_user.save(update_fields=["is_active"])

    persona.soft_delete()

    return None
```

---

## 14.6 POST /api/v1/personas/{persona_id}/clone

### Detail

Creates a deep copy of an existing Persona under a new name. The clone inherits all configuration (source_type, model/agent, tone, style, behavior, system_instructions) from the source persona. A new backing `identity_user` is created for the clone. The clone is always created in the same company as the source. Useful for creating persona variants or promoting a draft persona to production.

### Flow

1. Authenticate request; resolve `current_company`.
2. Fetch source `Persona` by `persona_id` scoped to `company`.
3. Validate the new `name` is unique within the company.
4. Create a new backing `User` record with `user_type=persona` for the clone.
5. Duplicate all Persona fields onto the new record, overriding `name` with the provided value.
6. Return the newly created (cloned) Persona detail.

### Request JSON

```json
{
  "name": "Aria — Formal Edition",
  "description": "A more formal variant of Aria for executive communications"
}
```

### Response JSON

```json
{
  "id": "pe2b3c4d-e5f6-7890-abcd-ef1234567891",
  "name": "Aria — Formal Edition",
  "description": "A more formal variant of Aria for executive communications",
  "source_type": "agent",
  "avatar_url": null,
  "tone": "friendly",
  "style": "concise",
  "behavior": "proactive",
  "system_instructions": "Always greet users by name. Keep responses under 3 sentences unless asked for detail.",
  "is_active": true,
  "model": null,
  "agent": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Support Agent",
    "agent_type": "internal",
    "max_steps": 10,
    "allow_parallel_tools": true
  },
  "identity_user": {
    "id": "u3b2c3d4-e5f6-7890-abcd-ef1234567892",
    "username": "aria_formal_edition_persona"
  },
  "created_by": {
    "id": "u2b2c3d4-e5f6-7890-abcd-ef1234567891",
    "username": "noaman@example.com"
  },
  "cloned_from": "pe1b2c3d-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-05-22T11:00:00Z",
  "updated_at": "2026-05-22T11:00:00Z"
}
```

### Pydantic for Django Ninja

```python
from ninja import Schema
from typing import Optional
from uuid import UUID
from datetime import datetime


class PersonaCloneIn(Schema):
    name: str
    description: Optional[str] = None


class PersonaCloneOut(Schema):
    id: UUID
    name: str
    description: Optional[str]
    source_type: str
    avatar_url: Optional[str]
    tone: Optional[str]
    style: Optional[str]
    behavior: Optional[str]
    system_instructions: Optional[str]
    is_active: bool
    model: Optional[AIModelBriefOut]
    agent: Optional[AIAgentBriefOut]
    identity_user: UserBriefOut
    created_by: Optional[UserBriefOut]
    cloned_from: UUID
    created_at: datetime
    updated_at: datetime
```

### Models Involved

- `Persona` — source record (read) + new cloned record (created)
- `User` — new `identity_user` created for the clone
- `AIModel` — FK copied from source (no new validation needed — same company)
- `AIAgent` — FK copied from source (no new validation needed — same company)
- `Company` — tenant scope

### Django ORM Query (Proposed)

```python
from django.db import transaction
from django.utils.text import slugify
from nucleus.models import Persona
from django.contrib.auth import get_user_model
from ninja.errors import HttpError

User = get_user_model()


@transaction.atomic
def clone_persona(request, persona_id, payload: PersonaCloneIn):
    company = request.auth.current_company
    created_by = request.auth

    # Fetch source persona
    try:
        source = Persona.objects.select_related(
            "model", "agent", "identity_user"
        ).get(
            id=persona_id,
            company=company,
            is_active=True,
        )
    except Persona.DoesNotExist:
        raise HttpError(404, "Persona not found.")

    # Validate new name is unique within company
    if Persona.objects.filter(company=company, name=payload.name, is_active=True).exists():
        raise HttpError(409, f"A persona named '{payload.name}' already exists in this company.")

    # Create backing identity user for the clone
    base_username = f"{slugify(payload.name)}_persona"
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{counter}"
        counter += 1

    identity_user = User.objects.create(
        username=username,
        email=f"{username}@persona.internal",
        user_type=User.UserType.PERSONA,
        is_active=True,
        current_company=company,
    )

    # Clone persona, overriding name, description, identity_user, created_by
    clone = Persona.objects.create(
        company=company,
        name=payload.name,
        description=payload.description if payload.description else source.description,
        source_type=source.source_type,
        model=source.model,
        agent=source.agent,
        identity_user=identity_user,
        created_by=created_by,
        # proposed fields — add after migration:
        # tone=source.tone,
        # style=source.style,
        # behavior=source.behavior,
        # system_instructions=source.system_instructions,
    )

    # Attach cloned_from reference in response (not persisted unless you add a FK field)
    clone._cloned_from = source.id

    return clone
```

---

## Summary: Proposed Model Additions

The following fields should be added to the `Persona` model in a new migration to support the full persona configuration surface (per api4.md):

```python
# Proposed additions to nucleus/models/intelligence.py → Persona

tone = models.CharField(
    max_length=50,
    null=True,
    blank=True,
    help_text="Communication tone: friendly, formal, casual, technical.",
)
style = models.CharField(
    max_length=50,
    null=True,
    blank=True,
    help_text="Response style: concise, verbose, bullet-points.",
)
behavior = models.CharField(
    max_length=50,
    null=True,
    blank=True,
    help_text="Interaction behavior: proactive, reactive, guided.",
)
system_instructions = models.TextField(
    null=True,
    blank=True,
    help_text="Free-text instructions layered on top of the underlying model/agent system prompt.",
)
```

Additionally, if you want to track clone lineage, add:

```python
cloned_from = models.ForeignKey(
    "self",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="clones",
    help_text="Source persona this was cloned from.",
)
```

| Proposed Field | Type | Purpose |
| --- | --- | --- |
| `tone` | `CharField(50)` | Communication tone (friendly, formal, technical) |
| `style` | `CharField(50)` | Response style (concise, verbose) |
| `behavior` | `CharField(50)` | Interaction behavior mode |
| `system_instructions` | `TextField` | Persona-level prompt layered over model/agent |
| `cloned_from` | `ForeignKey(self)` | Clone lineage tracking |
