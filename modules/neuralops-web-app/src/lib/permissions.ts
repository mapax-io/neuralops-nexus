// Gating by RIGHT, against the object the action targets. Every answer comes
// from the server (GET /api/v1/me/permissions/) — this module holds no rule
// about who may do what, and no role names. That is deliberate: role bundles
// are editable rows server-side (see Role in authn/permissions/models.py), so
// any client-side copy of them is wrong the moment someone edits one, and a
// company role could never express a project- or topic-scoped assignment
// anyway. A server too old to answer is surfaced as such — see usePermissions.
//
// The server enforces every action independently; these helpers only decide
// what to offer, so a hidden control is never the security boundary.
//
// Reach (company -> project -> topic) is resolved server-side and arrives
// pre-flattened in the payload: a project's list already contains anything
// inherited from a company assignment, a topic's anything from its project or
// company. So `can` is a flat lookup and deliberately does NOT walk the
// hierarchy — duplicating the reach rules in TypeScript is how the two drift.

/**
 * A right code, e.g. "persona.create".
 *
 * Deliberately an opaque string, NOT a union of the known codes: the registry
 * lives in authn/permissions/rights.py and is the server's to change. Mirroring
 * it here would be a second copy to keep in sync, and a stale copy is exactly
 * the failure this module exists to avoid. A call site names the one right it
 * needs; nothing in the client enumerates them.
 */
export type Right = string;

export type Scope =
  | { kind: "company" }
  | { kind: "project"; id: string }
  | { kind: "topic"; id: string };

/** Body of GET /api/v1/me/permissions/. An absent key means no rights there. */
export interface Permissions {
  company: { id: string; rights: string[] };
  projects: Record<string, string[]>;
  topics: Record<string, string[]>;
}

export const companyScope = (): Scope => ({ kind: "company" });
// id is optional so call sites can pass a not-yet-resolved route param without
// a guard — an empty id simply matches no key.
export const projectScope = (id: string | undefined | null): Scope => ({ kind: "project", id: id ?? "" });
export const topicScope = (id: string | undefined | null): Scope => ({ kind: "topic", id: id ?? "" });

export function can(perms: Permissions | undefined, right: Right, scope: Scope): boolean {
  // Nothing loaded means nothing known, and nothing known means nothing
  // offered. A control that appears and then vanishes is worse than one that
  // appears a moment late.
  if (!perms) return false;
  if (scope.kind === "company") return perms.company.rights.includes(right);
  if (scope.kind === "project") return (perms.projects[scope.id] ?? []).includes(right);
  return (perms.topics[scope.id] ?? []).includes(right);
}

/** True when the right is held on at least one project the payload lists. */
export function canAnyProject(perms: Permissions | undefined, right: Right): boolean {
  if (!perms) return false;
  return Object.values(perms.projects).some((rights) => rights.includes(right));
}
