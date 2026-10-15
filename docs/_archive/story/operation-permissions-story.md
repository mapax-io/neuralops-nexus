# NeuralOps — Operation Permissions Story

## The Problem

As NeuralOps grows, we need to control who can do what on every resource.
The naive approach is to hardcode a list of permissions somewhere. But that
breaks the moment you add a new feature — you have to remember to update the
list in multiple places.

We needed a system where:
- Permissions are tied to the models themselves
- Adding a new operation automatically applies to ALL relevant models
- No hardcoded lists anywhere
- Works with django-guardian for object-level permission checks later

---

## The Decision

Create an `Operation` abstract base class hierarchy in `base.py`.

Every model that inherits from it automatically gets a standard set of
operations registered in Django's permission system — without writing a
single line of extra code per model.

---

## The Design

```python
OPERATION_PERMISSIONS = (
    "add",      # create a new instance
    "view",     # read/list instances
    "change",   # update an instance
    "delete",   # delete an instance
    "invite",   # invite a user to this resource
    "remove",   # remove a user from this resource
    "archive",  # archive/unarchive this resource
    "join",     # join this resource as a participant
)
```

Three base classes, one for each scope:

```
OperationModel          → top-level (Company)
TenantOperationModel    → company-owned (Project, AIModel, MCPServer...)
ProjectOperationModel   → project-owned (Channel, ChatTopic, ChatMessage...)
```

---

## What Gets Created Automatically

For every model inheriting from Operation, Django creates:

```
add_{model}
view_{model}
change_{model}
delete_{model}
invite_{model}
remove_{model}
archive_{model}
join_{model}
```

Example for Project:
```
add_project
view_project
change_project
delete_project
invite_project
remove_project
archive_project
join_project
```

---

## Adding New Operations in Future

Just add one line to `OPERATION_PERMISSIONS` in `base.py`:

```python
OPERATION_PERMISSIONS = (
    ...existing...,
    "export",   # ← new operation
)
```

Run `makemigrations` + `migrate` → every model gets `export_{model}`.
No other changes needed anywhere.

---

## Models Upgraded to Operation

| Model | Base Class |
|---|---|
| Company | OperationModel |
| Project | TenantOperationModel |
| Channel | ProjectOperationModel |
| ChatTopic | ProjectOperationModel |
| ChatMessage | ProjectOperationModel |
| KnowledgeBase | TenantOperationModel |
| AIModel | TenantOperationModel |
| AIAgent | TenantOperationModel |
| MCPServer | TenantOperationModel |
| Persona | TenantOperationModel |

Models NOT upgraded (join tables / child records):
- CompanyAccess, ChatReaction, ChatReadMarker, ChatAttachment, ProjectMember

---

## What's Next

- Phase 1: Permission checks are simple (`is_owner` / `is_member`)
- Phase 2: Wire up django-guardian to assign these permissions per object
- Phase 3: UI for group management and permission assignment

The foundation is in place. No rewrites needed when Phase 2 and 3 come.

---

## Key Insight

> Permissions are defined on the model, not in a config file.
> The model knows what operations exist on it.
> django-guardian decides who has those operations on which instance.
