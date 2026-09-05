"""
authn/permissions/row_rules.py

Row-level visibility -- the Django-native equivalent of Odoo's ir.rule
"domain." Odoo stores a domain expression per (group, model) and lets
the ORM evaluate it dynamically at query time; here each rule is just a
plain Python function returning a queryset, since Django's ORM is
already the query language -- no separate domain DSL to invent or parse.

Distinct from PermissionChecker.can(): can() answers "may this user
act on THIS ONE object" (a boolean). These functions answer "which
objects can this user see at all" (an actual queryset -- could be
every object in the company, a handful, one, or none, depending on
what the user actually holds). Neither can substitute for the other.

No dispatcher/registry here on purpose -- callers just import and call
the function they need directly. A lookup table was tried and removed:
for a small, fixed set of functions it only added indirection an IDE
can't follow, with no real benefit -- see the design discussion this
is built from.
"""
from .checker import PermissionChecker
from .models import RoleAssignment


def _reachable_project_ids(user) -> set:
    """
    Every project id this user can reach via their own RoleAssignments --
    either directly (a project-scoped assignment) or indirectly (a
    topic-scoped assignment; that topic's parent project counts too, so
    the project still shows up as a navigation waypoint even though the
    user can't see its other channels/topics). Shared by every "narrow"
    fallback below, including the AI-resource ones which reuse the same
    "which projects can this user reach" question as the underlying
    visibility gate for models/agents/MCP servers attached to a project.
    """
    from nucleus.models import ChatTopic

    assignments = RoleAssignment.objects.filter(
        user=user, scope_object_type__in=["project", "topic"],
    )
    project_ids = {a.scope_object_id for a in assignments if a.scope_object_type == "project"}
    topic_ids = {a.scope_object_id for a in assignments if a.scope_object_type == "topic"}

    if topic_ids:
        project_ids |= set(
            ChatTopic.objects.filter(id__in=topic_ids).values_list("project_id", flat=True)
        )
    return project_ids


def _with_archived(user, qs, model, right_code):
    """
    Shared tail end for the three include_archived list functions below.
    `qs` is already scoped to the right company/project/channel and to
    the set of objects this user can see at all (broad: everything in
    scope; narrow: only the reachable ones) -- this just decides which
    of THOSE objects' archived rows also get included.

    Every active row in `qs` is included unconditionally (unrelated to
    archiving). Every archived row in `qs` is included only if the user
    holds `right_code` (project.archive / channel.archive / topic.archive)
    directly against that specific object -- same right that gates the
    archive action itself, checked per-object via PermissionChecker.can()
    so it correctly resolves for both a company-wide Owner/Admin (reaches
    every archived object in scope) and a Project Admin (reaches only the
    archived objects inside their own project), with no separate logic
    needed for the two cases.
    """
    active_ids = qs.filter(is_active=True).values_list("id", flat=True)
    archived_candidates = qs.filter(is_active=False)
    archived_ids = [
        obj.id for obj in archived_candidates
        if PermissionChecker.can(user, right_code, obj=obj)
    ]
    return model.objects.filter(id__in=list(active_ids) + archived_ids)


def visible_projects(user, company, include_archived=False):
    """
    Every Project this user can see.

    Broad case: user holds the company-wide 'project.list' right ->
    every project in the company (Owner/Admin territory).

    Narrow case: no broad right -> only the projects reachable from the
    user's own RoleAssignments (see _reachable_project_ids).

    include_archived=True additionally includes archived (is_active=False)
    projects the user specifically holds 'project.archive' against -- see
    _with_archived. Ordinary members/viewers never pass that check, so
    for them this parameter is a no-op.
    """
    from nucleus.models import Project

    if PermissionChecker.can(user, "project.list", company=company):
        qs = Project.objects.filter(company=company)
    else:
        project_ids = _reachable_project_ids(user)
        qs = Project.objects.filter(company=company, id__in=project_ids)

    if not include_archived:
        return qs.filter(is_active=True).order_by("name")
    return _with_archived(user, qs, Project, "project.archive").order_by("name")


def visible_channels(user, project, include_archived=False):
    """
    Every Channel in `project` this user can see.

    Broad case: user's assignment reaches 'channel.list' on this project
    (Project-scoped Admin/Member, or Company-scoped) -> every channel in it.

    Narrow case: user only holds a Topic-scoped assignment somewhere in
    this project -> only the channel(s) containing a topic they're
    actually scoped to. This is the same "waypoint, not full access"
    rule as visible_projects, one level down: the channel surfaces so
    they can navigate to their topic, but sibling topics/channels stay
    hidden -- enforced by visible_topics below, not here.

    include_archived=True additionally includes archived channels the user
    specifically holds 'channel.archive' against -- see _with_archived.
    """
    from nucleus.models import Channel, ChatTopic

    if PermissionChecker.can(user, "channel.list", obj=project):
        qs = Channel.objects.filter(project=project)
    else:
        topic_ids = set(
            RoleAssignment.objects.filter(
                user=user, scope_object_type="topic",
            ).values_list("scope_object_id", flat=True)
        )
        channel_ids = set()
        if topic_ids:
            channel_ids = set(
                ChatTopic.objects.filter(id__in=topic_ids, project=project).values_list("channel_id", flat=True)
            )
        qs = Channel.objects.filter(project=project, id__in=channel_ids)

    if not include_archived:
        return qs.filter(is_active=True).order_by("name")
    return _with_archived(user, qs, Channel, "channel.archive").order_by("name")


def visible_topics(user, channel, include_archived=False):
    """
    Every ChatTopic in `channel` this user can see.

    Broad case: user's assignment reaches 'topic.list' on this channel's
    project (Project-scoped or Company-scoped) -> every topic in it.

    Narrow case: only the specific topic(s) the user holds a direct
    Topic-scoped RoleAssignment on -- this is the actual enforcement
    point for "invited to one topic, can't see sibling topics."

    include_archived=True additionally includes archived topics the user
    specifically holds 'topic.archive' against -- see _with_archived.
    """
    from nucleus.models import ChatTopic

    if PermissionChecker.can(user, "topic.list", obj=channel):
        qs = ChatTopic.objects.filter(channel=channel)
    else:
        topic_ids = set(
            RoleAssignment.objects.filter(
                user=user, scope_object_type="topic",
            ).values_list("scope_object_id", flat=True)
        )
        qs = ChatTopic.objects.filter(channel=channel, id__in=topic_ids)

    if not include_archived:
        return qs.filter(is_active=True).order_by("created_at")
    return _with_archived(user, qs, ChatTopic, "topic.archive").order_by("created_at")


# ── AI resources (Model Config / MCP Server) ───────────────────────────────────
# ModelConfig is company-owned (created/deleted only by a company-scope
# admin -- see intelligence/api.py) with VISIBILITY project-gated via its
# `projects` M2M. A config with no projects attached is invisible to
# everyone without the broad company-wide right, including its own creator
# -- attachment is a separate, explicit step (model_config.attach).
#
# MCPServer is different now: it owns a real `project` FK rather than an
# M2M, so its narrow path is a plain column filter with no join and no
# .distinct().
#
# visible_agents() is GONE -- AIAgent no longer exists.

def visible_model_configs(user, company):
    """
    Broad case: 'model_config.list' company-wide right -> every config in the
    company.
    Narrow case: only configs attached (via the `projects` M2M) to a project
    this user can reach.
    """
    from nucleus.models import ModelConfig

    if PermissionChecker.can(user, "model_config.list", company=company):
        return ModelConfig.objects.filter(company=company, is_active=True).order_by("name")

    project_ids = _reachable_project_ids(user)
    return ModelConfig.objects.filter(
        company=company, is_active=True, projects__id__in=project_ids,
    ).distinct().order_by("name")


def visible_mcp_servers(user, company):
    """
    Same broad/narrow shape as visible_model_configs, but MCP servers are
    single-project by FK (see MCPServer in nucleus/models/intelligence.py),
    so the narrow path filters project_id directly. No M2M join, therefore
    no duplicate rows and no .distinct() needed.
    """
    from nucleus.models import MCPServer

    if PermissionChecker.can(user, "mcp_server.list", company=company):
        return MCPServer.objects.filter(company=company, is_active=True).order_by("name")

    project_ids = _reachable_project_ids(user)
    return MCPServer.objects.filter(
        company=company, is_active=True, project_id__in=project_ids,
    ).order_by("name")


def visible_personas(user, project):
    """
    Every Persona in `project` this user can see.

    Unlike the three functions above, Persona is exclusively single-project
    (a real FK, not an M2M -- see nucleus/models/intelligence.py), and the
    API always resolves one specific project before calling this (list
    endpoint takes project_id as a required param) -- so the shape here is
    (user, project), not (user, company).

    Broad case: user holds the company-wide 'persona.list' right -> sees
    personas in any project, including this one.
    Narrow case: no broad right -> only if this project is one the user can
    reach via their own RoleAssignments (i.e. they're actually a member of
    it) -- otherwise nothing, not even a peek. This is what was missing
    before: previously the API 403'd anyone without the company-wide right,
    even a plain member of this exact project.
    """
    from nucleus.models import Persona

    if PermissionChecker.can(user, "persona.list", company=project.company):
        return Persona.objects.filter(project=project, is_active=True).order_by("name")

    if project.id in _reachable_project_ids(user):
        return Persona.objects.filter(project=project, is_active=True).order_by("name")

    return Persona.objects.none()
