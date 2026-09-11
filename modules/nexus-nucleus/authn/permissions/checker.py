"""
authn/permissions/checker.py

PermissionChecker — the ONE class every view/service calls to grant or
deny an action. Nothing else in the codebase should make a permission
decision directly (no more scattered user.has_perm(...) calls, no more
hand-rolled CompanyAccess.role / ProjectMember.role / TopicParticipant.role
checks). If a new kind of check is needed, it's a new Right in
authn/permissions/rights.py, not a new if-statement somewhere else.

Usage from an api.py view:

    from authn.permissions.checker import PermissionChecker

    if not PermissionChecker.can(request.auth, "project.create", company=company):
        raise HttpError(403, "You don't have permission to create projects.")

    ...

"Which rows may this user SEE at all" is a different question, and a
different module: authn/permissions/row_rules.py.

    from authn.permissions.row_rules import visible_projects

    projects = visible_projects(request.auth, company)

(This docstring used to show a PermissionChecker.objects_of_type() example.
No such method has ever existed -- following it raised AttributeError.)
"""
from django.db.models import Q

from .models import Right, Role, RoleAssignment, RoleRight, ScopeType

# Reach ordering: lower number = broader = reaches further down.
# A RoleAssignment at a given scope can grant any Right whose own `scope`
# is the same level or narrower (i.e. equal or higher number).
_SCOPE_ORDER = {
    ScopeType.COMPANY: 0,
    ScopeType.PROJECT: 1,
    ScopeType.TOPIC: 2,
}


def _scope_chain(obj):
    """
    Given a model instance, return the list of (scope_level, object_id)
    pairs that a RoleAssignment could be anchored at to reach it —
    the object itself plus every ancestor above it in the hierarchy.

    Example: a ChatTopic's chain is
        [(TOPIC, topic.id), (PROJECT, topic.project_id), (COMPANY, topic.company_id)]
    because an assignment scoped to the topic itself, OR to its project,
    OR to its company, all reach that topic (reach flows downward).

    Lazy-imports nucleus.models to avoid a circular import at Django
    startup (same lazy-import pattern already used throughout
    workspace/services.py, chat/services.py, etc. in this codebase).
    """
    from nucleus.models import Company, Project, Channel, ChatTopic, MCPServer

    if isinstance(obj, Company):
        return [(ScopeType.COMPANY, obj.id)]

    if isinstance(obj, Project):
        return [
            (ScopeType.PROJECT, obj.id),
            (ScopeType.COMPANY, obj.company_id),
        ]

    if isinstance(obj, Channel):
        # Channels are not their own assignable scope — reach comes from
        # the parent Project (or that project's Company).
        return [
            (ScopeType.PROJECT, obj.project_id),
            (ScopeType.COMPANY, obj.company_id),
        ]

    if isinstance(obj, ChatTopic):
        return [
            (ScopeType.TOPIC, obj.id),
            (ScopeType.PROJECT, obj.project_id),
            (ScopeType.COMPANY, obj.company_id),
        ]

    if isinstance(obj, MCPServer):
        # Owned by exactly ONE project through a real `project` FK -- the old
        # `projects` M2M was dropped in the AIAgent collapse, and AIAgent
        # (the other member of this branch) is gone entirely. The FK is
        # non-null in the schema, so there is no .first()/None dance any
        # more; the guard below only covers an in-memory instance that has
        # not been saved yet, which falls through to the COMPANY-only case.
        if obj.project_id:
            return [
                (ScopeType.PROJECT, obj.project_id),
                (ScopeType.COMPANY, obj.company_id),
            ]

    # Company-wide resources: anything with a plain `company` FK and no
    # project boundary. Persona is project-owned via a real FK but never
    # reaches this function directly -- intelligence/api.py always checks
    # persona rights with obj=persona.project, so a Project lands here, not
    # a Persona. ModelConfig DOES belong here on purpose: it is genuinely
    # company-shared and attachable to many projects, see rights.py. These
    # only reach through COMPANY scope, on purpose -- see the big comment
    # block in rights.py about why a Project-scoped Admin must NOT inherit
    # model_config.create/delete this way (model_config.attach is the one
    # exception, and that's checked with obj=project, not obj=config, so it
    # never hits this fallback either).
    company_id = getattr(obj, "company_id", None)
    if company_id:
        return [(ScopeType.COMPANY, company_id)]

    return []


def _matching_assignments(user, chain, right_scope):
    """
    Every RoleAssignment this user holds that (a) is anchored at one of
    the scopes in `chain`, and (b) is broad enough to reach `right_scope`.
    """
    eligible = [
        (level, obj_id) for level, obj_id in chain
        if _SCOPE_ORDER[level] <= _SCOPE_ORDER[right_scope]
    ]
    if not eligible:
        return RoleAssignment.objects.none()

    q = Q()
    for level, obj_id in eligible:
        q |= Q(scope_object_type=level, scope_object_id=obj_id)

    return RoleAssignment.objects.filter(q, user=user).select_related("role")


class PermissionChecker:
    """
    Namespace class — every method is a staticmethod/classmethod, there's
    no instance state. Kept as a class (rather than bare module functions)
    purely so call sites read as `PermissionChecker.can(...)`, making it
    obvious at a glance that this is THE permission system, not just some
    helper function.
    """

    @staticmethod
    def can(user, right_code: str, obj=None, company=None) -> bool:
        """
        The core check. Returns True/False — never raises for "access
        denied" (callers decide whether that means HttpError(403),
        HttpError(404), or silently filtering something out of a list).

        Pass `obj` when checking against a specific existing object
        (a Project, Channel, ChatTopic, Persona, ...). Pass `company`
        instead when checking a right that doesn't have an object yet
        (e.g. "project.create" — there's no Project instance until after
        the check passes).
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return False

        right = Right.objects.filter(code=right_code).first()
        if right is None:
            # Fail loudly in development — an unregistered right code is
            # a bug (typo, or someone forgot to add it to rights.py),
            # not a legitimate "access denied".
            raise ValueError(
                f"Unknown right code '{right_code}'. "
                f"Add it to authn/permissions/rights.py and run manage.py seed_permissions."
            )

        if obj is not None:
            chain = _scope_chain(obj)
        elif company is not None:
            chain = [(ScopeType.COMPANY, company.id)]
        else:
            chain = []

        if not chain:
            return False

        assignments = _matching_assignments(user, chain, right.scope)
        if not assignments.exists():
            return False

        role_ids = assignments.values_list("role_id", flat=True)
        return RoleRight.objects.filter(role_id__in=role_ids, right=right).exists()

    @staticmethod
    def _rights_from_chains(user, chains: dict) -> dict:
        """
        The one implementation of "which rights does this user hold against
        each of these objects". Takes {key: scope_chain} and answers
        {key: set(codes)} in TWO queries, whatever the number of objects.

        Both rights_for() and rights_for_many() go through here, so the reach
        rule lives in exactly one place -- see the module docstring.
        """
        if user is None or not getattr(user, "is_authenticated", False):
            return {key: set() for key in chains}

        anchors = {(level, str(obj_id)) for chain in chains.values() for level, obj_id in chain}
        if not anchors:
            return {key: set() for key in chains}

        rows = RoleAssignment.objects.filter(user=user).filter(
            Q(*[
                Q(scope_object_type=level, scope_object_id=obj_id)
                for level, obj_id in anchors
            ], _connector=Q.OR)
        ).values_list("scope_object_type", "scope_object_id", "role_id")

        roles_at = {}
        role_ids = set()
        for level, obj_id, role_id in rows:
            roles_at.setdefault((level, str(obj_id)), set()).add(role_id)
            role_ids.add(role_id)
        if not role_ids:
            return {key: set() for key in chains}

        # (code, scope) per role, so the reach test below is pure Python.
        rights_of = {}
        for role_id, code, scope in RoleRight.objects.filter(
            role_id__in=role_ids
        ).values_list("role_id", "right__code", "right__scope"):
            rights_of.setdefault(role_id, []).append((code, scope))

        out = {}
        for key, chain in chains.items():
            held = set()
            for level, obj_id in chain:
                anchor_order = _SCOPE_ORDER[level]
                for role_id in roles_at.get((level, str(obj_id)), ()):
                    for code, scope in rights_of.get(role_id, ()):
                        # An assignment grants a right only if the right's own
                        # scope is the same level or narrower. Without this an
                        # assignment reports every right on its role -- so a
                        # topic-scoped role claimed company-scoped rights that
                        # can() denies, and the two disagreed.
                        if anchor_order <= _SCOPE_ORDER[scope]:
                            held.add(code)
            out[key] = held
        return out

    @staticmethod
    def rights_for(user, obj=None, company=None) -> set:
        """
        Every right code this user holds against `obj` (or `company`),
        across ALL of their applicable role assignments combined (the
        "union of stacked roles" behaviour).

        Agrees with can() by construction: a right appears here if and only
        if can() would return True for it against the same object.
        """
        chain = _scope_chain(obj) if obj is not None else (
            [(ScopeType.COMPANY, company.id)] if company else []
        )
        if not chain:
            return set()
        return PermissionChecker._rights_from_chains(user, {"_": chain})["_"]

    @staticmethod
    def rights_for_many(user, objs) -> dict:
        """
        rights_for() for a batch, keyed by each object's id, in a fixed two
        queries rather than two per object. Built for the /me/permissions/
        payload, which resolves every visible project and topic at once.
        """
        chains = {}
        for obj in objs:
            chain = _scope_chain(obj)
            if chain:
                chains[str(obj.id)] = chain
        if not chains:
            return {}
        return PermissionChecker._rights_from_chains(user, chains)

    @staticmethod
    def assign_role(user, role: Role, obj, granted_by=None) -> RoleAssignment:
        """
        Grant `role` to `user` on `obj` (a Company / Project / ChatTopic
        instance). Does not remove any other role the user already holds
        at this or any other scope — assignments are additive/stackable
        by design (see RoleAssignment docstring in models.py).
        """
        chain = _scope_chain(obj)
        if not chain:
            raise ValueError(f"Cannot determine a scope for {obj!r}.")
        scope_level, scope_id = chain[0]  # the object's own scope, not its ancestors

        assignment, _created = RoleAssignment.objects.get_or_create(
            user=user,
            role=role,
            scope_object_type=scope_level,
            scope_object_id=scope_id,
            defaults={"granted_by": granted_by},
        )
        return assignment

    @staticmethod
    def revoke_role(user, role: Role, obj) -> int:
        """Remove `role` from `user` on `obj`. Returns number of rows deleted (0 or 1)."""
        chain = _scope_chain(obj)
        if not chain:
            return 0
        scope_level, scope_id = chain[0]
        deleted, _ = RoleAssignment.objects.filter(
            user=user, role=role,
            scope_object_type=scope_level, scope_object_id=scope_id,
        ).delete()
        return deleted
