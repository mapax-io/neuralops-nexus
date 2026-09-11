import { http, HttpResponse } from "msw";
import type { Permissions } from "@/lib/permissions";

// Fixture data: the codes these suites exercise, standing in for a server
// response. NOT imported by app code -- nothing in src/lib or src/components
// enumerates rights, so this list can go stale without misleading the app.
export const ALL_RIGHTS = [
  "company.invite_member", "company.remove_member",
  "project.create", "project.list", "project.view", "project.archive",
  "channel.create", "channel.list", "channel.update", "channel.archive",
  "topic.create", "topic.list", "topic.update", "topic.mark_read", "topic.archive",
  "session.create", "session.close",
  "persona.mention", "persona.list", "persona.create", "persona.update", "persona.delete",
  "mcp_server.list", "mcp_server.create", "mcp_server.update", "mcp_server.delete",
  "model_config.list", "model_config.create", "model_config.update", "model_config.delete",
  "model_config.attach",
  "schedule.create", "schedule.manage",
];

/**
 * A /me/permissions/ handler granting everything on the named objects — the
 * "you administer this" fixture most component suites want. Pass the project
 * and topic ids the suite uses; an id that is not listed reads as no rights,
 * which is what the negative cases rely on.
 */
export function grantAll(base: string, { projects = [], topics = [] }: { projects?: string[]; topics?: string[] } = {}) {
  const payload: Permissions = {
    company: { id: "c-fixture", rights: [...ALL_RIGHTS] },
    projects: Object.fromEntries(projects.map((id) => [id, [...ALL_RIGHTS]])),
    topics: Object.fromEntries(topics.map((id) => [id, [...ALL_RIGHTS]])),
  };
  return http.get(`${base}/api/v1/me/permissions/`, () => HttpResponse.json(payload));
}

/** A /me/permissions/ handler granting nothing — a plain member's payload. */
export function grantNone(base: string) {
  return grant(base, { company: { id: "c-fixture", rights: [] }, projects: {}, topics: {} });
}

/** A /me/permissions/ handler granting exactly what is passed. */
export function grant(base: string, payload: Permissions) {
  return http.get(`${base}/api/v1/me/permissions/`, () => HttpResponse.json(payload));
}
