import { describe, expect, it } from "vitest";
import {
  channelState, fromGrants, projectState, pruneGrants, summarize, toGrants, toggleChannel, toggleProject,
  toggleTopic, topicChecked, type ProjectShape, type Selection,
} from "./invite-grants";

// Alpha: general {t1, t2}, design {t3}, empty channel {}. Beta: no channels.
const alpha: ProjectShape = {
  id: "p1", name: "Alpha",
  channels: [
    { id: "c1", name: "general", topics: [{ id: "t1", title: "chat#1" }, { id: "t2", title: "chat#2" }] },
    { id: "c2", name: "design", topics: [{ id: "t3", title: "chat#3" }] },
    { id: "c3", name: "empty", topics: [] },
  ],
};
const beta: ProjectShape = { id: "p2", name: "Beta", channels: [] };
const none: Selection = {};

describe("invite-grants — the selection model behind the tree", () => {
  it("checking a project means the whole project; checking again clears it", () => {
    const on = toggleProject(none, alpha);
    expect(on).toEqual({ p1: "all" });
    expect(projectState(on, "p1")).toBe("checked");
    expect(topicChecked(on, alpha, "t3")).toBe(true);
    expect(channelState(on, alpha, "c1")).toBe("checked");
    expect(toggleProject(on, alpha)).toEqual({});
  });

  it("unchecking one topic of a whole project narrows it to the rest", () => {
    const sel = toggleTopic(toggleProject(none, alpha), alpha, "t2");
    expect(sel).toEqual({ p1: ["t1", "t3"] });
    expect(projectState(sel, "p1")).toBe("mixed");
    expect(channelState(sel, alpha, "c1")).toBe("mixed");
    expect(channelState(sel, alpha, "c2")).toBe("checked");
    expect(topicChecked(sel, alpha, "t2")).toBe(false);
  });

  it("checking topics one by one until every topic is on becomes the whole project again", () => {
    let sel = toggleTopic(none, alpha, "t1");
    expect(sel).toEqual({ p1: ["t1"] });
    sel = toggleTopic(sel, alpha, "t2");
    sel = toggleTopic(sel, alpha, "t3");
    expect(sel).toEqual({ p1: "all" });
  });

  it("unchecking the last topic drops the project entirely", () => {
    const sel = toggleTopic(toggleTopic(none, alpha, "t1"), alpha, "t1");
    expect(sel).toEqual({});
    expect(projectState(sel, "p1")).toBe("unchecked");
  });

  it("a channel checkbox selects or clears all of its topics", () => {
    const on = toggleChannel(none, alpha, "c1");
    expect(on).toEqual({ p1: ["t1", "t2"] });
    expect(channelState(on, alpha, "c1")).toBe("checked");
    expect(channelState(on, alpha, "c2")).toBe("unchecked");
    // Partly selected → checking the channel completes it; fully selected → clears it.
    const partial = toggleTopic(none, alpha, "t1");
    expect(toggleChannel(partial, alpha, "c1")).toEqual({ p1: ["t1", "t2"] });
    expect(toggleChannel(on, alpha, "c1")).toEqual({});
    // Clearing one channel of a whole project leaves the others.
    expect(toggleChannel(toggleProject(none, alpha), alpha, "c1")).toEqual({ p1: ["t3"] });
  });

  it("a channel with no topics cannot be toggled", () => {
    expect(toggleChannel(none, alpha, "c3")).toEqual({});
    expect(channelState(none, alpha, "c3")).toBe("unchecked");
  });

  it("a project with no topics can only be the whole project", () => {
    const sel = toggleProject(none, beta);
    expect(sel).toEqual({ p2: "all" });
    expect(toGrants(sel)).toEqual([{ project_id: "p2", topic_ids: [] }]);
  });

  it("projects are independent of each other", () => {
    const sel = toggleTopic(toggleProject(none, beta), alpha, "t3");
    expect(sel).toEqual({ p2: "all", p1: ["t3"] });
    expect(toggleProject(sel, beta)).toEqual({ p1: ["t3"] });
  });

  it("produces the server's grants shape, in a stable order", () => {
    const sel = toggleTopic(toggleProject(none, beta), alpha, "t2");
    expect(toGrants(sel)).toEqual([
      { project_id: "p2", topic_ids: [] },
      { project_id: "p1", topic_ids: ["t2"] },
    ]);
    expect(toGrants(none)).toEqual([]);
  });

  it("summarizes what will be granted in plain words", () => {
    expect(summarize(none, [alpha, beta])).toBe("");
    expect(summarize(toggleProject(none, alpha), [alpha, beta])).toBe("Alpha (whole project)");
    expect(summarize(toggleTopic(none, alpha, "t2"), [alpha, beta])).toBe("Alpha (1 of 3 topics)");
    expect(summarize(toggleTopic(toggleProject(none, beta), alpha, "t2"), [alpha, beta]))
      .toBe("Beta (whole project) · Alpha (1 of 3 topics)");
  });

  it("is unaffected by a topic it does not know about (a stale id from before a reload)", () => {
    const stale: Selection = { p1: ["t1", "gone"] };
    expect(topicChecked(stale, alpha, "t1")).toBe(true);
    expect(projectState(stale, "p1")).toBe("mixed");
    expect(toggleTopic(stale, alpha, "t1")).toEqual({});
  });

  it("round-trips grants back into a selection", () => {
    const sel: Selection = { p2: "all", p1: ["t2"] };
    expect(fromGrants(toGrants(sel))).toEqual(sel);
  });
});

describe("pruneGrants — what the app already knows is gone", () => {
  it("drops a project that is no longer listed", () => {
    expect(pruneGrants([{ project_id: "p9", topic_ids: [] }, { project_id: "p1", topic_ids: [] }], [alpha])).toEqual([
      { project_id: "p1", topic_ids: [] },
    ]);
  });

  it("drops topic ids the project no longer has, and the whole grant when none are left — never widening it", () => {
    expect(pruneGrants([{ project_id: "p1", topic_ids: ["t1", "gone"] }], [alpha])).toEqual([{ project_id: "p1", topic_ids: ["t1"] }]);
    expect(pruneGrants([{ project_id: "p1", topic_ids: ["gone"] }], [alpha])).toEqual([]);
  });

  it("passes through a grant for a project whose topics are not known — the server validates it", () => {
    expect(pruneGrants([{ project_id: "p2", topic_ids: ["x"] }], [beta])).toEqual([{ project_id: "p2", topic_ids: ["x"] }]);
  });
});
