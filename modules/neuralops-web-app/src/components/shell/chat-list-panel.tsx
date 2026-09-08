"use client";

import { useState } from "react";
import { Archive, MessageSquarePlus, MessageSquareText, PanelRightClose, Plus, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { useArchiveTopic, useCreateTopic, useProjects, useTopics } from "@/hooks/use-workspace";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelection } from "@/stores/selection.store";
import { useUiStore } from "@/stores/ui.store";

// The channel's TOPICS live here, on the right of the conversation (thread-
// panel anatomy) — the left tree stays Projects → Channels only.
export function ChatListPanel({ pid, cid }: { pid: string; cid: string }) {
  const { sel, setTopic, clearTopic } = useSelection();
  const toggleChatsPanel = useUiStore((u) => u.toggleChatsPanel);
  const role = useConnectionStore((s) => s.connection?.role);
  const { data: projects } = useProjects();
  const project = projects?.find((p) => p.id === pid);
  // topic.create rides the PROJECT tier now (DECISIONS §23).
  const canCreate = role !== "viewer";
  // topic.archive is a PROJECT-scope Admin right (Member/Viewer never get it).
  const canManage = isCompanyAdmin(role);
  const channelName = project?.channels.find((c) => c.id === cid)?.name;
  const { data: topics, isLoading, error, refetch } = useTopics(pid, cid);
  const showLoading = useDelayedLoading(isLoading);
  const [archiving, setArchiving] = useState<{ id: string; title: string } | null>(null);
  const create = useCreateTopic(pid, cid, (t) => setTopic(t.project_id, t.channel_id, t.id));
  const archive = useArchiveTopic(pid, cid, () => {
    /* if the archived chat was open, TopicView's 404 state guides back */
  });

  return (
    <aside aria-label="Topics in this channel" className="flex h-full min-h-0 flex-1 flex-col bg-rail">
      <header className="flex h-12 flex-none items-center gap-2 border-b border-line px-4">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[13.5px] font-semibold leading-tight">Topics</h2>
          {channelName && <p className="truncate text-[11px] leading-tight text-ink2">#{channelName}</p>}
        </div>
        {canCreate && (
          <button
            aria-label={`New topic${channelName ? ` in ${channelName}` : ""}`}
            title="New topic"
            disabled={!topics || create.isPending} /* deriving chat#N from a half-loaded list would mint duplicates */
            onClick={() => create.mutate(topics?.map((t) => t.title) ?? [])}
            className="flex size-7 flex-none items-center justify-center rounded-lg border border-line bg-surface text-ink2 hover:border-accent hover:text-ink disabled:opacity-40"
          >
            <Plus size={14} strokeWidth={2} />
          </button>
        )}
        {sel?.tid && (
          <button
            aria-label="Collapse the topics panel"
            title="Collapse"
            onClick={toggleChatsPanel}
            className="hidden size-7 flex-none items-center justify-center rounded-lg text-ink2 hover:bg-surface hover:text-ink lg:flex"
          >
            <PanelRightClose size={14} strokeWidth={2} />
          </button>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {(isLoading || showLoading) &&
          (showLoading ? (
            <div className="flex flex-col gap-2 p-1.5" role="status" aria-label="Loading topics">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
              <Skeleton className="h-9 w-3/4" />
            </div>
          ) : null)}
        {!!error && (
          <p className="px-2 py-3 text-[12.5px] text-crit">
            Couldn&apos;t load topics.{" "}
            <button className="underline hover:text-ink" onClick={() => refetch()}>Retry</button>
          </p>
        )}
        {!isLoading && !showLoading && !error && topics?.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<MessageSquarePlus strokeWidth={1.8} />}
              title="No topics yet"
              hint="Topics are cheap — they name themselves after the first message."
              action={
                canCreate ? (
                  <Button size="sm" variant="primary" loading={create.isPending} onClick={() => create.mutate([])}>
                    <MessageSquarePlus size={14} strokeWidth={2} /> Start the first topic
                  </Button>
                ) : undefined
              }
            />
          </div>
        )}
        {!showLoading && !!topics?.length && (
          <ul className="flex flex-col gap-0.5">
            {topics.map((t) => {
              const active = t.id === sel?.tid;
              return (
                <li key={t.id} className={`group flex items-center rounded-lg pr-1 ${active ? "bg-accent/10" : "hover:bg-surface"}`}>
                  <button
                    onClick={() => setTopic(t.project_id, t.channel_id, t.id)}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-w-0 flex-1 items-start gap-2 px-2.5 py-2 text-left text-[13px] ${active ? "font-semibold text-ink" : "text-ink2 hover:text-ink"}`}
                  >
                    <MessageSquareText aria-hidden size={13.5} strokeWidth={2} className={`mt-[2px] flex-none ${active ? "text-accent" : "text-ink2/70"}`} />
                    {/* Full title, wrapped — never an ellipsis. */}
                    <span className={`min-w-0 flex-1 break-words leading-snug ${t.has_unread && !active ? "font-semibold text-ink" : ""}`}>{t.title}</span>
                    {(t.unread_count ?? 0) > 0 && !active && (
                      <span aria-label={`${t.unread_count} unread messages`} className="mt-[1px] flex h-[16px] min-w-[16px] flex-none items-center justify-center rounded-full bg-accent px-1 text-[9.5px] font-bold leading-none text-accent-ink">
                        {(t.unread_count ?? 0) > 99 ? "99+" : t.unread_count}
                      </span>
                    )}
                  </button>
                  {canManage && (
                    <button
                      aria-label={`Archive topic ${t.title}`}
                      title="Archive topic"
                      onClick={() => setArchiving({ id: t.id, title: t.title })}
                      className="flex size-6 flex-none items-center justify-center rounded text-ink2 hover:text-crit opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
                    >
                      <Trash2 size={12.5} strokeWidth={2} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={!!archiving}
        onClose={() => setArchiving(null)}
        onConfirm={() => {
          if (archiving) {
            if (sel?.tid === archiving.id) clearTopic();
            archive.mutate(archiving.id);
          }
          setArchiving(null);
        }}
        title="Archive this topic?"
        body={
          <p>
            <b className="text-ink">{archiving?.title}</b> will be hidden for the whole team, along with its
            messages. A server admin can restore it later.
          </p>
        }
        confirmLabel="Archive topic"
        confirmIcon={<Archive size={14} strokeWidth={2} />}
        loading={archive.isPending}
      />
    </aside>
  );
}
