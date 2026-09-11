import type { Grant } from "@/lib/api/members";

// The selection behind the invite tree, and the grants it becomes. Pure:
// the tree renders these and calls the toggles; nothing here fetches.

export interface TopicShape { id: string; title: string }
export interface ChannelShape { id: string; name: string; topics: TopicShape[] }
export interface ProjectShape { id: string; name: string; channels: ChannelShape[] }

// projectId → "all" (the whole project, topics created later included) or
// the chosen topic ids. A project with no entry is not part of the invite.
export type Selection = Record<string, "all" | string[]>;
export type CheckState = "checked" | "mixed" | "unchecked";

const allTopicIds = (p: ProjectShape) => p.channels.flatMap((c) => c.topics.map((t) => t.id));

function chosen(sel: Selection, p: ProjectShape): Set<string> {
  const v = sel[p.id];
  if (!v) return new Set();
  return new Set(v === "all" ? allTopicIds(p) : v);
}

// Collapse an explicit set back into the model: nothing → the project is out;
// every topic the project has → the whole project; otherwise the list. Ids the
// project no longer has (a stale selection) are dropped on the way.
function settle(sel: Selection, p: ProjectShape, ids: Set<string>): Selection {
  const known = allTopicIds(p);
  const kept = known.filter((id) => ids.has(id));
  const next = { ...sel };
  if (kept.length === 0) delete next[p.id];
  else if (kept.length === known.length) next[p.id] = "all";
  else next[p.id] = kept;
  return next;
}

export function toggleProject(sel: Selection, p: ProjectShape): Selection {
  const next = { ...sel };
  if (next[p.id]) delete next[p.id];
  else next[p.id] = "all";
  return next;
}

export function toggleTopic(sel: Selection, p: ProjectShape, topicId: string): Selection {
  const ids = chosen(sel, p);
  if (ids.has(topicId)) ids.delete(topicId);
  else ids.add(topicId);
  return settle(sel, p, ids);
}

// A channel is not a scope the server knows; its box just moves all of its
// topics at once — on unless every one already is, off otherwise.
export function toggleChannel(sel: Selection, p: ProjectShape, channelId: string): Selection {
  const topicIds = p.channels.find((c) => c.id === channelId)?.topics.map((t) => t.id) ?? [];
  if (topicIds.length === 0) return sel;
  const ids = chosen(sel, p);
  const every = topicIds.every((id) => ids.has(id));
  for (const id of topicIds) {
    if (every) ids.delete(id);
    else ids.add(id);
  }
  return settle(sel, p, ids);
}

export function projectState(sel: Selection, projectId: string): CheckState {
  const v = sel[projectId];
  return !v ? "unchecked" : v === "all" ? "checked" : "mixed";
}

export function channelState(sel: Selection, p: ProjectShape, channelId: string): CheckState {
  const topicIds = p.channels.find((c) => c.id === channelId)?.topics.map((t) => t.id) ?? [];
  if (topicIds.length === 0) return "unchecked";
  const ids = chosen(sel, p);
  const on = topicIds.filter((id) => ids.has(id)).length;
  return on === 0 ? "unchecked" : on === topicIds.length ? "checked" : "mixed";
}

export const topicChecked = (sel: Selection, p: ProjectShape, topicId: string): boolean => chosen(sel, p).has(topicId);

// The server's shape: an empty topic_ids is the whole project.
export function toGrants(sel: Selection): Grant[] {
  return Object.entries(sel).map(([project_id, v]) => ({ project_id, topic_ids: v === "all" ? [] : v }));
}

export function fromGrants(grants: Grant[]): Selection {
  return Object.fromEntries(grants.map((g) => [g.project_id, g.topic_ids.length ? g.topic_ids : "all"]));
}

// Drop what the app already knows is gone — a project no longer listed, a
// topic no longer in its project — rather than send an id the server will
// refuse. A topic list emptied this way drops the grant; it is never widened
// to the whole project. A project whose topics are not known is passed
// through; the server validates it.
export function pruneGrants(grants: Grant[], known: ProjectShape[]): Grant[] {
  const out: Grant[] = [];
  for (const g of grants) {
    const p = known.find((x) => x.id === g.project_id);
    if (!p) continue;
    const ids = allTopicIds(p);
    if (g.topic_ids.length === 0 || ids.length === 0) {
      out.push(g);
      continue;
    }
    const kept = g.topic_ids.filter((id) => ids.includes(id));
    if (kept.length) out.push({ project_id: g.project_id, topic_ids: kept });
  }
  return out;
}

export function summarize(sel: Selection, projects: ProjectShape[]): string {
  return Object.entries(sel)
    .map(([projectId, v]) => {
      const p = projects.find((x) => x.id === projectId);
      const name = p?.name ?? "Project";
      if (v === "all") return `${name} (whole project)`;
      const total = p ? allTopicIds(p).length : v.length;
      return `${name} (${v.length} of ${total} topic${total === 1 ? "" : "s"})`;
    })
    .join(" · ");
}
