"""
authn/permissions/models.py

The four tables that make up the whole permission system.

    Right          — flat registry of "things that can be done"
    Role           — a named bundle of Rights, with a stated philosophy
    RoleRight      — join table: which Rights a Role grants
    RoleAssignment — join table: which user holds which Role, scoped to
                     a specific Company / Project / ChatTopic

These are plain Django models living in the `authn` app (so they migrate
under the `authn` app label), but the actual class definitions are kept
in this dedicated `authn/permissions/` folder instead of the app's main
models.py, to keep all permission-related code in one place. They are
imported into authn/models.py so Django's app registry / migration
autodetector can find them under `authn.models` as usual — see the
bottom of authn/models.py for that one-line bridge import.
"""
import uuid

from django.conf import settings
from django.db import models


class ScopeType(models.TextChoices):
    """
    The three levels a Role / RoleAssignment can apply at.

    Reach flows DOWNWARD only: a Role granted at COMPANY scope reaches
    every Project and every ChatTopic inside that company. A Role granted
    at PROJECT scope reaches that project and every ChatTopic inside it
    (channels are not their own assignable scope — they inherit from
    their Project). A Role granted at TOPIC scope reaches only that one
    ChatTopic and nothing else — no visibility into sibling topics.

    This ordering (COMPANY broadest -> TOPIC narrowest) is used by
    PermissionChecker to decide whether an assignment at a given scope
    is allowed to grant a Right that is defined for a narrower (or equal)
    scope. See SCOPE_ORDER in checker.py.
    """
    COMPANY = "company", "Company"
    PROJECT = "project", "Project"
    TOPIC = "topic", "Topic"


class ObjectType(models.TextChoices):
    """
    The kinds of object a Right can apply to. Purely descriptive /
    organizational — used to group rights in the registry and in any
    admin UI — PermissionChecker does not branch on this field directly,
    it only matters for humans reading the Right table.
    """
    PROJECT = "project", "Project"
    CHANNEL = "channel", "Channel"
    TOPIC = "topic", "Chat Topic"
    SESSION = "session", "Chat Session"
    PERSONA = "persona", "Persona"
    MCP_SERVER = "mcp_server", "MCP Server"
    MODEL_CONFIG = "model_config", "Model Config"
    COMPANY = "company", "Company"
    SCHEDULE = "schedule", "Persona Schedule"
    # REMOVED: AGENT -- AIAgent is gone; Persona absorbed it.
    # RENAMED:  AI_MODEL -> MODEL_CONFIG, matching the model rename.


class Right(models.Model):
    """
    One row per action that exists in the system. This IS the "list of
    rights" — the full registry lives here, not scattered as string
    literals across every api.py file.

    `code` is the identifier used everywhere else (e.g. "project.create").
    See authn/permissions/rights.py for the full seed list and the
    management command that loads it (`manage.py seed_permissions`).

    `scope` is the NARROWEST scope this right can be granted at. Example:
    "project.create" has scope=COMPANY, because creating a brand new
    project isn't something a role scoped to one already-existing project
    can reach "up" to do. "session.create" has scope=TOPIC, because it
    can be granted narrowly (just this topic) or broadly (a Company- or
    Project-scoped role also reaches down to it) — see ScopeType above.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    code = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Stable identifier, e.g. 'project.create'. Referenced by code everywhere, never by id.",
    )
    object_type = models.CharField(max_length=20, choices=ObjectType.choices)
    scope = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        help_text="Narrowest scope level this right can be granted at. See ScopeType docstring.",
    )
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "authn_right"
        ordering = ["object_type", "code"]

    def __str__(self) -> str:
        return self.code


class Role(models.Model):
    """
    A named, philosophy-driven bundle of Rights (see RoleRight for the
    actual rights it grants).

    Every company gets four roles seeded automatically when it's created
    (Owner, Admin, Member, Viewer — see the seed_permissions management
    command) but nothing about this table treats those four specially.
    A company can rename them, change their rights, or add entirely new
    roles (e.g. a "Builder" role holding only persona/agent/mcp_server/
    ai_model creation rights) — a Role is just a row like any other.
    There is deliberately no "is_system" flag: PermissionChecker never
    needs to know how a role came to exist, only what rights it has.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        "nucleus.Company",
        on_delete=models.CASCADE,
        related_name="roles",
        help_text="Every role belongs to exactly one company. Custom roles are always company-specific.",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(
        blank=True,
        help_text="The philosophy — why this role exists and what it's meant to represent.",
    )
    scope = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        help_text="Which level this role is meant to be assigned at (Company / Project / Topic).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "authn_role"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name", "scope"],
                name="uniq_role_name_per_company_scope",
            )
        ]
        ordering = ["company", "scope", "name"]

    def __str__(self) -> str:
        return f"{self.company.name} / {self.name} ({self.scope})"


class RoleRight(models.Model):
    """
    Join table: which Rights a Role grants. This is the actual "rights
    matrix" — Owner has N rows here, Member has fewer, a custom "Builder"
    role has exactly the handful it needs.

    Editing what a Role means is editing rows here, once — every
    RoleAssignment that points at this Role picks up the change
    immediately. Nothing is ever copied per-object (that was the
    django-guardian / per-object-Group problem this design avoids).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_rights")
    right = models.ForeignKey(Right, on_delete=models.CASCADE, related_name="role_rights")

    class Meta:
        db_table = "authn_role_right"
        constraints = [
            models.UniqueConstraint(fields=["role", "right"], name="uniq_role_right"),
        ]

    def __str__(self) -> str:
        return f"{self.role.name} -> {self.right.code}"


class RoleAssignment(models.Model):
    """
    Join table: which user holds which Role, scoped to one specific
    object (a Company, a Project, or a ChatTopic).

    `scope_object_type` + `scope_object_id` point at that object using a
    plain string + UUID pair (the same pattern already used elsewhere in
    this codebase for generic references — see AuditEvent.target_type /
    EmbeddingJob.target_type in nucleus/models/extended.py — rather than
    Django's ContentType/GenericForeignKey framework, to stay consistent
    with the rest of the app).

    A user CAN hold more than one RoleAssignment at the same scope at
    once (e.g. Member + a "Persona Creator" capability role on the same
    Project). PermissionChecker takes the UNION of every Role reachable
    from every RoleAssignment a user holds — see checker.py. This is how
    small, additive "capability" roles are stacked on top of a base tier
    without ever needing to copy or fork a role definition.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")

    scope_object_type = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        help_text="Which kind of object this assignment is scoped to (company / project / topic).",
    )
    scope_object_id = models.UUIDField(
        help_text="The id of that Company / Project / ChatTopic instance.",
    )

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_role_assignments",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "authn_role_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "scope_object_type", "scope_object_id"],
                name="uniq_user_role_scope",
            )
        ]
        indexes = [
            models.Index(fields=["user", "scope_object_type", "scope_object_id"]),
            models.Index(fields=["scope_object_type", "scope_object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} as {self.role.name} on {self.scope_object_type}:{self.scope_object_id}"
