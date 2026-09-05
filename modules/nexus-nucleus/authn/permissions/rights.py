"""
authn/permissions/rights.py

The full Right registry, as plain Python data. This is the list you
asked for early on — one place listing every action that exists in the
system, before any of it touches the database.

Nothing here talks to Django's ORM. `manage.py seed_permissions` (see
authn/management/commands/seed_permissions.py) reads REGISTRY and
create-or-updates the matching `Right` rows, and seeds the four default
Roles (Owner / Admin / Member / Viewer) with their default RoleRight
sets for a given company.

To add a new right: add one line to REGISTRY, then re-run
`manage.py seed_permissions`. Nothing else needs to change for the right
to exist — you still have to decide which default role(s) get it, in
DEFAULT_ROLE_RIGHTS below.
"""
from .models import ObjectType, ScopeType

# ── The registry ──────────────────────────────────────────────────────────────
# (code, object_type, scope, description)
#
# `scope` = the NARROWEST level this right can be granted at. A right
# scoped to TOPIC can also be granted via a broader PROJECT or COMPANY
# assignment (reach flows downward) — see ScopeType docstring in models.py.
REGISTRY = [
    # ── Company ─────────────────────────────────────────────────────────────
    ("company.invite_member", ObjectType.COMPANY, ScopeType.COMPANY,
     "Invite a new user to join the company."),
    ("company.remove_member", ObjectType.COMPANY, ScopeType.COMPANY,
     "Remove a user from the company entirely."),

    # ── Project ─────────────────────────────────────────────────────────────
    # create/list are COMPANY-scope: there's no existing project to "reach up"
    # from when the project doesn't exist yet.
    ("project.create", ObjectType.PROJECT, ScopeType.COMPANY,
     "Create a new project."),
    ("project.list", ObjectType.PROJECT, ScopeType.COMPANY,
     "List every project this user has visibility into."),
    # view/delete can be granted at PROJECT scope directly (someone made
    # Owner/Admin of just one project) as well as inherited from COMPANY.
    ("project.view", ObjectType.PROJECT, ScopeType.PROJECT,
     "View a specific project's details."),
    ("model_config.attach", ObjectType.PROJECT, ScopeType.PROJECT,
     "Attach an already-existing model config to a project (does not create "
     "the config or touch its API key -- that's model_config.create, "
     "COMPANY-only). Reachable by a Project-scoped Admin, unlike "
     "model_config.create/delete. This is the right that lets a company "
     "Owner/Admin share one set of credentials across projects."),
    ("project.archive", ObjectType.PROJECT, ScopeType.PROJECT,
     "Archive (soft-delete) a project, or view it once archived. Reversible in "
     "principle via Project.restore() -- there's just no endpoint for that yet. "
     "Same right gates both archiving and the include_archived view."),

    # ── Channel ─────────────────────────────────────────────────────────────
    # Channels are not their own assignable scope — they're always reached
    # through their parent Project.
    ("channel.create", ObjectType.CHANNEL, ScopeType.PROJECT,
     "Create a new channel inside a project."),
    ("channel.list", ObjectType.CHANNEL, ScopeType.PROJECT,
     "List the channels inside a project."),
    ("channel.update", ObjectType.CHANNEL, ScopeType.PROJECT,
     "Rename / edit a channel's description. (No update endpoint exists yet as of this writing.)"),
    ("channel.archive", ObjectType.CHANNEL, ScopeType.PROJECT,
     "Archive (soft-delete) a channel, or view it once archived. Same right "
     "gates both archiving and the include_archived view."),

    # ── MCP Server -- project-owned, so PROJECT scope (reachable by both a
    # company-wide Admin and that project's own Project Admin). Distinct
    # from model_config.* below, which stays COMPANY-only. ───────────────────
    ("mcp_server.update", ObjectType.MCP_SERVER, ScopeType.PROJECT,
     "Edit an MCP server belonging to a project."),

    # ── Chat Topic ──────────────────────────────────────────────────────────
    ("topic.create", ObjectType.TOPIC, ScopeType.PROJECT,
     "Create a new topic inside a channel. Reaches down from Project scope."),
    ("topic.list", ObjectType.TOPIC, ScopeType.PROJECT,
     "List the topics inside a channel."),
    ("topic.update", ObjectType.TOPIC, ScopeType.TOPIC,
     "Rename a topic. Grantable narrowly (this topic only) or from a broader scope."),
    ("topic.mark_read", ObjectType.TOPIC, ScopeType.TOPIC,
     "Mark a topic as read for yourself."),
    ("topic.archive", ObjectType.TOPIC, ScopeType.TOPIC,
     "Archive (soft-delete) a topic, or view it once archived. Same right "
     "gates both archiving and the include_archived view."),

    # ── Chat Session (the @session mechanism) ──────────────────────────────
    ("session.create", ObjectType.SESSION, ScopeType.TOPIC,
     "Open an AI session against one or more personas within a topic."),
    ("session.close", ObjectType.SESSION, ScopeType.TOPIC,
     "Close an active AI session in a topic."),

    # ── Persona mention (using AI, distinct from managing Persona records) ─
    ("persona.mention", ObjectType.PERSONA, ScopeType.TOPIC,
     "Trigger an AI response by @mentioning a persona in a topic."),

    # ── AI Intelligence infrastructure — COMPANY scope ONLY. ───────────────
    # These resources have no project boundary (see workspace API routes:
    # /api/v1/personas/, /api/v1/mcp-servers/, /api/v1/agents/,
    # /api/v1/ai-models/ — none take a project_id). A Project-scoped Admin
    # must NOT inherit these: creating one of these affects the whole
    # company, not just one project. Only a COMPANY-scoped assignment can
    # grant them.
    # agent.list stays COMPANY -- reachability for ordinary project members
    # comes through the row-visibility fallback (visible_agents), same as
    # mcp_server.list below, not through this right being held directly.
    ("persona.list", ObjectType.PERSONA, ScopeType.COMPANY, "List personas."),
    
    # create/update/delete are PROJECT scope -- a persona belongs to exactly one
    # project, and that project's own Admin should be able to manage it without
    # needing company-wide access (aligned with agent.* and mcp_server.*).
    ("persona.create", ObjectType.PERSONA, ScopeType.PROJECT, "Create a persona in a project."),
    ("persona.update", ObjectType.PERSONA, ScopeType.PROJECT, "Edit a persona."),
    ("persona.delete", ObjectType.PERSONA, ScopeType.PROJECT, "Delete a persona."),

    # agent.list / agent.create / agent.update / agent.delete were REMOVED --
    # AIAgent no longer exists. Persona absorbed it: a persona is one model
    # config, an optional advisor, and zero or more MCP servers. Their Right
    # rows and every RoleRight referencing them are deleted in
    # authn/migrations/0005 -- seed_permissions only ever create-or-updates,
    # so dropping them from this REGISTRY alone would leave them granted in
    # the database forever.

    ("mcp_server.list", ObjectType.MCP_SERVER, ScopeType.COMPANY, "List MCP servers."),
    ("mcp_server.create", ObjectType.MCP_SERVER, ScopeType.PROJECT, "Register a new MCP server in a project."),
    ("mcp_server.delete", ObjectType.MCP_SERVER, ScopeType.PROJECT, "Delete an MCP server."),

    ("model_config.list", ObjectType.MODEL_CONFIG, ScopeType.COMPANY, "List model configs."),
    ("model_config.create", ObjectType.MODEL_CONFIG, ScopeType.COMPANY, "Register a new model config."),
    ("model_config.update", ObjectType.MODEL_CONFIG, ScopeType.COMPANY,
     "Edit a model config -- including rotating its API key. Previously "
     "impossible: there was no update endpoint, and delete is refused while "
     "any persona still references the row."),
    ("model_config.delete", ObjectType.MODEL_CONFIG, ScopeType.COMPANY, "Delete a model config."),

    # ── Persona Schedule (#189) — TOPIC scope, same tier as session.create/
    # persona.mention: any Member with access to a topic can automate a
    # persona there, no elevated role needed. schedule.manage is separate
    # from schedule.create on purpose -- a Member who created a schedule can
    # always pause/delete THEIR OWN one via an ownership check in
    # scheduling/services.py (PersonaSchedule.created_by == user), independent
    # of holding this right. schedule.manage is what lets someone act on a
    # schedule they did NOT create (e.g. an Admin cleaning up after someone
    # who left) -- same shape as topic.archive being separate from topic.create.
    ("schedule.create", ObjectType.SCHEDULE, ScopeType.TOPIC,
     "Create a recurring or one-time automated persona query in a topic."),
    ("schedule.manage", ObjectType.SCHEDULE, ScopeType.TOPIC,
     "Pause, resume, or delete any schedule in a topic, including ones you did not create."),
]


# ── Default rights per seeded role ─────────────────────────────────────────────
# Keyed by role name. Used by seed_permissions to build the starting
# RoleRight rows for the four default roles every company gets. These are
# a starting point, not a hard rule — a company can edit them afterward,
# same as any other Role.
#
# Deliberately excluded from MEMBER and VIEWER: persona/agent/mcp_server/
# ai_model create+delete rights, and project.archive/channel.archive/
# topic.archive — matches everything decided in design discussion (Member
# never gets company-wide infra rights regardless of scope; only Owner/Admin
# do; archiving is an Admin-tier action, unlike the old Owner-only
# project.delete it replaces).
DEFAULT_ROLE_RIGHTS = {
    "Owner": [code for code, *_ in REGISTRY],  # everything, no exceptions

    "Admin": [
        "company.invite_member", "company.remove_member",
        "project.create", "project.list", "project.view", "project.archive",
        "channel.create", "channel.list", "channel.update", "channel.archive",
        "topic.create", "topic.list", "topic.update", "topic.mark_read", "topic.archive",
        "session.create", "session.close",
        "persona.mention",
        "persona.list", "persona.create", "persona.update", "persona.delete",
        "mcp_server.list", "mcp_server.create", "mcp_server.update", "mcp_server.delete",
        "model_config.list", "model_config.create", "model_config.update",
        "model_config.delete", "model_config.attach",
        "schedule.create", "schedule.manage",
        # project.archive/channel.archive/topic.archive are now included --
        # this reverses the old project.delete-was-Owner-only policy. Archiving
        # is reversible (soft-delete + unused Model.restore()) so it's no
        # longer treated as irreversible/Owner-tier. Each right also gates
        # the include_archived view for that resource (same right, two jobs).
        #
        # ai_model.attach is also granted at PROJECT scope to a Project Admin
        # (see PermissionChecker._scope_chain -- Project.company_id reaches
        # this from the project object). Company Admin has it too via this
        # COMPANY-scope assignment. Same for agent.create/delete/update and
        # mcp_server.create/delete/update, which are PROJECT-scope rights
        # reachable here from COMPANY, and also directly grantable to a
        # Project-scoped Admin RoleAssignment.
    ],

    "Member": [
        "project.list", "project.view",
        "channel.list",
        "topic.create", "topic.list", "topic.update", "topic.mark_read",
        "session.create", "session.close",
        "persona.mention",
        "persona.list", "mcp_server.list", "model_config.list",
        "schedule.create",
        # Deliberately no schedule.manage -- a Member can still pause/delete
        # a schedule THEY created via the ownership check in
        # scheduling/services.py, just not one someone else created.
    ],

    "Viewer": [
        "project.list", "project.view",
        "channel.list",
        "topic.list", "topic.mark_read",
        "persona.list", "mcp_server.list", "model_config.list",
        # Deliberately no session.*, no persona.mention, no *.create/update/delete.
        # topic.mark_read is the one exception: it's a personal read-state
        # marker, not a write to shared content, so every role gets it.
    ],
}
