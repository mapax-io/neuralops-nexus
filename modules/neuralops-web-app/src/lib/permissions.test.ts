import { describe, expect, it } from "vitest";
import { can, canAnyProject, companyScope, projectScope, topicScope, type Permissions } from "./permissions";

// Shaped exactly like GET /api/v1/me/permissions/: every list is already
// resolved server-side, so p1's entry includes anything inherited from the
// company assignment and t1's includes anything inherited from p1.
const PERMS: Permissions = {
  company: { id: "c1", rights: ["project.list", "persona.list", "company.invite_member"] },
  projects: {
    p1: ["project.view", "channel.create", "persona.create", "mcp_server.create"],
    p2: ["project.view"],
  },
  topics: {
    t1: ["topic.mark_read", "topic.update", "persona.mention", "session.create"],
  },
};

describe("can — company scope", () => {
  it("is true for a right in the company list", () => {
    expect(can(PERMS, "company.invite_member", companyScope())).toBe(true);
  });

  it("is false for a right the company list omits", () => {
    expect(can(PERMS, "company.remove_member", companyScope())).toBe(false);
  });
});

describe("can — project scope", () => {
  it("is true for a right on that project", () => {
    expect(can(PERMS, "persona.create", projectScope("p1"))).toBe(true);
  });

  it("is false for the same right on a different project", () => {
    expect(can(PERMS, "persona.create", projectScope("p2"))).toBe(false);
  });

  it("is false for a project that is not a key at all — absent means no rights there", () => {
    expect(can(PERMS, "project.view", projectScope("p99"))).toBe(false);
  });
});

describe("can — topic scope", () => {
  it("is true for a right on that topic", () => {
    expect(can(PERMS, "persona.mention", topicScope("t1"))).toBe(true);
  });

  it("is false for a topic that is not a key", () => {
    expect(can(PERMS, "topic.mark_read", topicScope("t99"))).toBe(false);
  });
});

describe("can — no scope arithmetic", () => {
  // The server resolves reach; the client does a flat lookup and never walks
  // company -> project -> topic itself. These two assertions are what keep
  // that honest.
  it("does not fall through from company to project", () => {
    expect(can(PERMS, "project.list", projectScope("p1"))).toBe(false);
  });

  it("does not fall through from project to company", () => {
    expect(can(PERMS, "persona.create", companyScope())).toBe(false);
  });
});

describe("can — nothing loaded", () => {
  it("is false at every scope when perms are undefined", () => {
    expect(can(undefined, "company.invite_member", companyScope())).toBe(false);
    expect(can(undefined, "persona.create", projectScope("p1"))).toBe(false);
    expect(can(undefined, "persona.mention", topicScope("t1"))).toBe(false);
  });

  it("is false for an empty id rather than throwing", () => {
    expect(can(PERMS, "project.view", projectScope(undefined))).toBe(false);
    expect(can(PERMS, "topic.update", topicScope(undefined))).toBe(false);
  });
});

describe("canAnyProject", () => {
  it("is true when at least one project carries the right", () => {
    expect(canAnyProject(PERMS, "persona.create")).toBe(true);
  });

  it("is false when no project carries it", () => {
    expect(canAnyProject(PERMS, "model_config.attach")).toBe(false);
  });

  it("does not consult the company list", () => {
    expect(canAnyProject(PERMS, "company.invite_member")).toBe(false);
  });

  it("is false when nothing is loaded", () => {
    expect(canAnyProject(undefined, "persona.create")).toBe(false);
  });
});
