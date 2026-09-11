"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Checkbox, FieldError } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/surfaces";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { useProjectTopics, useProjects, useProjectsTopics, type ChannelTopics } from "@/hooks/use-workspace";
import type { Project } from "@/lib/api/workspace";
import {
  channelState, projectState, summarize, toggleChannel, toggleProject, toggleTopic, topicChecked,
  type ProjectShape, type Selection,
} from "@/lib/invite-grants";

// Projects → channels → topics, each with a box. A project's box is the whole
// project (topics created later included); unticking topics narrows it to
// just those; a channel's box moves all of its topics at once. Every state
// is spoken: projects loading/failed/none, topics loading/failed/none.
export function InviteAccessTree({ selection, onChange, idPrefix }: {
  selection: Selection;
  onChange: (next: Selection) => void;
  idPrefix: string;
}) {
  const { data: projects, isPending, error, refetch } = useProjects();
  // The summary needs each picked project's topic count; same cache the rows fill.
  const { byProject } = useProjectsTopics(Object.keys(selection));
  // Delayed and held: the list is usually cached by the sidebar, and a
  // skeleton that flashes for a few frames reads as a glitch.
  const showLoader = useDelayedLoading(isPending);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const setOpen = (id: string, open: boolean) =>
    setExpanded((cur) => {
      const next = new Set(cur);
      if (open) next.add(id);
      else next.delete(id);
      return next;
    });

  if (isPending) {
    return showLoader ? (
      <div className="flex flex-col gap-2" role="status" aria-label="Loading projects">
        <Skeleton className="h-7" />
        <Skeleton className="h-7 w-4/5" />
      </div>
    ) : null;
  }
  if (error) {
    return (
      <FieldError>
        Couldn&apos;t load projects.{" "}
        <button type="button" onClick={() => refetch()} className="underline hover:text-ink">Retry</button>
      </FieldError>
    );
  }
  if (!projects?.length) {
    return <p className="text-[12.5px] text-ink2">No projects on this server yet — they get server access only.</p>;
  }

  const summary = summarize(selection, projects.map((p) => toShape(p, byProject[p.id] ?? [])));
  return (
    <div>
      <ul className="overflow-hidden rounded-[10px] border border-line bg-surface px-3 py-1">
        {projects.map((p) => (
          <ProjectRow
            key={p.id}
            id={`${idPrefix}-${p.id}`}
            project={p}
            selection={selection}
            expanded={expanded.has(p.id)}
            onExpand={(open) => setOpen(p.id, open)}
            onChange={onChange}
          />
        ))}
      </ul>
      <p className="mt-1.5 text-[12px] text-ink2" data-testid="invite-summary">
        {summary || "No project picked — they get server access only."}
      </p>
    </div>
  );
}

const toShape = (project: Project, groups: ChannelTopics[]): ProjectShape => ({
  id: project.id,
  name: project.name,
  channels: groups.map((g) => ({ id: g.channel.id, name: g.channel.name, topics: g.topics.map((t) => ({ id: t.id, title: t.title })) })),
});

function ProjectRow({ id, project, selection, expanded, onExpand, onChange }: {
  id: string;
  project: Project;
  selection: Selection;
  expanded: boolean;
  onExpand: (open: boolean) => void;
  onChange: (next: Selection) => void;
}) {
  const state = projectState(selection, project.id);
  // Topics are only fetched once the row is opened or the project is part of
  // the invite — never for every project on the server up front.
  const { loading, error, retry, groups } = useProjectTopics(expanded || state !== "unchecked" ? project.id : undefined);
  const showLoader = useDelayedLoading(loading);
  const shape = toShape(project, groups);
  const panelId = `${id}-topics`;
  return (
    <li className="border-b border-line last:border-b-0">
      <div className="flex items-center gap-2 py-2">
        <Checkbox
          checked={state === "checked"}
          indeterminate={state === "mixed"}
          onToggle={() => {
            onChange(toggleProject(selection, shape));
            // Show what "the whole project" covers the moment it is picked.
            if (state === "unchecked") onExpand(true);
          }}
          label={`Add to ${project.name}`}
        />
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => onExpand(!expanded)}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13.5px] font-medium text-ink transition-colors hover:text-accent"
        >
          <ChevronRight size={14} strokeWidth={2} className={`flex-none text-ink2 transition-transform ${expanded ? "rotate-90" : ""}`} />
          <span className="truncate">{project.name}</span>
          {state === "checked" && <span className="ml-auto flex-none text-[11px] font-normal text-ink2">whole project</span>}
        </button>
      </div>
      {expanded && (
        <div id={panelId} className="mb-2 ml-[9px] border-l border-line pl-4">
          {loading ? (
            showLoader ? <p className="py-1 text-[12px] text-ink2">Loading topics…</p> : null
          ) : error ? (
            <FieldError>
              Couldn&apos;t load topics.{" "}
              <button type="button" onClick={retry} className="underline hover:text-ink">Retry</button>
            </FieldError>
          ) : shape.channels.length === 0 ? (
            <p className="py-1 text-[12px] text-ink2">No channels yet — the whole project is the only option.</p>
          ) : (
            shape.channels.map((c) => {
              const cs = channelState(selection, shape, c.id);
              return (
                <div key={c.id} className="py-1">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={cs === "checked"}
                      indeterminate={cs === "mixed"}
                      disabled={c.topics.length === 0}
                      onToggle={() => onChange(toggleChannel(selection, shape, c.id))}
                      label={`Add to every topic in #${c.name}`}
                    />
                    <span className="text-[13px] text-ink">#{c.name}</span>
                    {c.topics.length === 0 && <span className="text-[11px] text-ink2">no topics yet</span>}
                  </div>
                  {c.topics.length > 0 && (
                    <ul className="ml-[9px] border-l border-line pl-4">
                      {c.topics.map((t) => (
                        <li key={t.id} className="flex items-center gap-2 py-1">
                          <Checkbox
                            checked={topicChecked(selection, shape, t.id)}
                            onToggle={() => onChange(toggleTopic(selection, shape, t.id))}
                            label={`Add to ${t.title}`}
                          />
                          <span className="truncate text-[13px] text-ink">{t.title}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </li>
  );
}
