"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { TeamDialog } from "@/components/shell/team-dialog";
import type { ChatTab } from "@/components/chat/chat-tabs";
import { ChatHeaderBar } from "@/components/chat/chat-header-bar";
import { Composer } from "@/components/chat/composer";
import { ContextPanel } from "@/components/chat/context-panel";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { McpTab } from "@/components/intelligence/mcp-tab";
import { ModelsTab } from "@/components/intelligence/models-tab";
import { PersonasTab } from "@/components/intelligence/personas-tab";
import { isCompanyAdmin } from "@/lib/permissions";
import { Button } from "@/components/ui/button";
import { SessionBanner } from "@/components/chat/session-banner";
import { MessageList } from "@/components/chat/message-list";
import { SchedulesPanel } from "@/components/chat/schedules-panel";
import { TypingBar } from "@/components/chat/typing-bar";
import { useChat } from "@/hooks/use-chat";
import { useMarkTopicRead, useProjects, useTopics } from "@/hooks/use-workspace";
import { useConnectionStore } from "@/stores/connection.store";
import { useSearchShortcut } from "@/lib/platform";
import { useSelection } from "@/stores/selection.store";
import { useUiStore } from "@/stores/ui.store";

// The open chat. Ids come from the selection store, never the URL.
export function TopicView({ pid, cid, tid }: { pid: string; cid: string; tid: string }) {
  const { clearTopic } = useSelection();
  const panelCollapsed = useUiStore((u) => u.chatsPanelCollapsed);
  const toggleChatsPanel = useUiStore((u) => u.toggleChatsPanel);
  const role = useConnectionStore((s) => s.connection?.role);
  // Participation comes from the PROJECT tier (DECISIONS §23): a server
  // Viewer who is a project Member CAN post here; a server Member on no
  // team is read-only.
  const participates = role !== "viewer";
  const { data: projects } = useProjects();
  const { data: topics } = useTopics(pid, cid);
  const markRead = useMarkTopicRead();
  const project = projects?.find((p) => p.id === pid);
  const channel = project?.channels.find((c) => c.id === cid);
  const topic = topics?.find((t) => t.id === tid);
  const chat = useChat(pid, cid, tid, topic?.title);
  const [endingSession, setEndingSession] = useState(false);
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const [tab, setTab] = useState<ChatTab>("messages");
  // Slash-command dialogs host the REAL intelligence tabs over the chat —
  // create/edit/delete complete right here, no navigation (owner decision).
  const [slashDialog, setSlashDialog] = useState<"models" | "mcp" | "personas" | null>(null);
  const [jumpTo, setJumpTo] = useState<string | null>(null);
  const [membersOpen, setMembersOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchIdx, setMatchIdx] = useState(0);
  const shortcut = useSearchShortcut();
  const sq = searchQuery.trim().toLowerCase();
  const matches = sq ? chat.messages.filter((m) => !m.isSystem && m.content.toLowerCase().includes(sq)).map((m) => m.id) : [];
  // Escape closes the search bar from anywhere in the chat. Innermost
  // consumers (dialogs, composer popovers/menus) mark the event consumed via
  // preventDefault; this bubble-phase listener only sees unclaimed Escapes.
  useEffect(() => {
    if (!searchOpen) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      setSearchOpen(false);
    };
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [searchOpen]);
  // Results can shrink without typing (history load rehomes an orphan reply)
  // — clamp before displaying or cycling so "5/3" is impossible.
  const shownIdx = matches.length ? Math.min(matchIdx, matches.length - 1) : 0;
  const gotoMatch = (idx: number) => {
    if (!matches.length) return;
    const next = ((idx % matches.length) + matches.length) % matches.length;
    setMatchIdx(next);
    setJumpTo(matches[next]);
  };
  // Adjust-during-render: switching chats always lands on Messages.
  const [lastTid, setLastTid] = useState(tid);
  if (tid !== lastTid) {
    setLastTid(tid);
    setTab("messages");
    setJumpTo(null);
    setSearchOpen(false);
    setSearchQuery("");
    setMatchIdx(0);
  }

  // Keep the read marker current while the topic is open — on entry and as
  // new messages land (debounced by the id of the newest message).
  const newestId = chat.messages.at(-1)?.id;
  useEffect(() => {
    if (pid && cid && tid) {
      markRead.mutate({ projectId: pid, channelId: cid, topicId: tid });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- per topic + newest message
  }, [tid, newestId]);

  if (chat.loadErrorStatus === 404) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <h1 className="font-display text-[19px] font-extrabold">This chat isn&apos;t available</h1>
        <p className="max-w-sm text-[13.5px] text-ink2">It may have been archived or removed, or you may not have access to it.</p>
        <Button size="sm" onClick={clearTopic}>Back to the channel</Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Slack-anatomy header: title row, then a tab strip. */}
      <ChatHeaderBar membersPid={pid}
        title={topic?.title ?? "…"}
        projectName={project?.name}
        channelName={channel?.name}
        onBack={clearTopic}
        panelCollapsed={panelCollapsed}
        onTogglePanel={toggleChatsPanel}
        connection={chat.connection}
        loading={chat.loading}
        onMembers={() => setMembersOpen(true)}
        searchOpen={searchOpen}
        onToggleSearch={() => {
          setSearchOpen((o) => !o);
          setSearchQuery("");
          setMatchIdx(0);
        }}
        searchShortcut={shortcut}
        tab={tab}
        onTab={setTab}
      />
      {searchOpen && (
        <div className="flex flex-none items-center gap-2 border-b border-line bg-bg2/60 px-4 py-2">
          <Search size={14} strokeWidth={2} className="flex-none text-ink2" />
          <input
            autoFocus
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setMatchIdx(0);
              const q = e.target.value.trim().toLowerCase();
              const first = q ? chat.messages.find((m) => !m.isSystem && m.content.toLowerCase().includes(q)) : undefined;
              if (first) setJumpTo(first.id);
              if (tab !== "messages") setTab("messages");
            }}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return; // IME Enter/Escape belong to the composition
              if (e.key === "Escape") {
                e.preventDefault(); // consumed — the document-level listener must not react too
                setSearchOpen(false);
              }
              if (e.key === "Enter") gotoMatch(e.shiftKey ? shownIdx - 1 : shownIdx + 1);
            }}
            placeholder="Search in this chat…"
            aria-label="Search in this chat"
            className="w-full bg-transparent text-[13.5px] outline-none placeholder:text-ink2/60"
          />
          <span title="Counts matches in the loaded messages" className="flex-none font-mono text-[11.5px] tabular-nums text-ink2">
            {sq ? (matches.length ? `${shownIdx + 1}/${matches.length}` : "0/0") : ""}
          </span>
          <button aria-label="Previous match" disabled={!matches.length} onClick={() => gotoMatch(shownIdx - 1)} className="flex size-6 flex-none items-center justify-center rounded text-ink2 hover:bg-surface hover:text-ink disabled:opacity-30">
            <ChevronUp size={14} strokeWidth={2} />
          </button>
          <button aria-label="Next match" disabled={!matches.length} onClick={() => gotoMatch(shownIdx + 1)} className="flex size-6 flex-none items-center justify-center rounded text-ink2 hover:bg-surface hover:text-ink disabled:opacity-30">
            <ChevronDown size={14} strokeWidth={2} />
          </button>
          <button aria-label="Close search" onClick={() => setSearchOpen(false)} className="flex size-6 flex-none items-center justify-center rounded text-ink2 hover:bg-surface hover:text-ink">
            <X size={14} strokeWidth={2} />
          </button>
        </div>
      )}
      {tab === "schedules" ? (
        <div key="schedules" className="nx-pane flex min-h-0 flex-1 flex-col"><SchedulesPanel pid={pid} cid={cid} tid={tid} /></div>
      ) : tab === "context" ? (
        <ContextPanel
          projectId={pid}
          topicId={tid}
          onViewInChat={(id) => {
            setTab("messages");
            setJumpTo(id);
          }}
        />
      ) : (
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="relative flex min-h-0 flex-1 flex-col">
              <MessageList
              key={tid}
              messages={chat.messages}
              transitions={chat.transitions}
              loading={chat.loading}
              loadError={chat.loadError}
              onRetry={chat.refetch}
              onLoadOlder={chat.loadOlder}
              jumpToId={jumpTo}
              onJumped={() => setJumpTo(null)}
              totalLoaded={chat.totalLoaded}
            />
              <TypingBar actors={chat.typing} />
            </div>
            <SessionBanner messages={chat.messages} ending={endingSession} onEnd={participates ? () => setConfirmingEnd(true) : undefined} />
            {!participates ? (
              /* Viewer is read-only: no posting, no sessions, no @mentions
                 (rights.py gives Viewer no create/session/mention rights). */
              <p role="note" className="flex-none border-t border-line bg-bg2/60 px-4 py-3 text-center text-[12.5px] text-ink2">
                You have view-only access to this workspace — you can read along, but not post.
              </p>
            ) : (
              <Composer projectId={pid} channelId={cid} topicId={tid} channelName={channel?.name} topicTitle={topic?.title} onSend={chat.send}  onShowSchedules={() => setTab("schedules")} onSlashDialog={setSlashDialog} />
            )}
          </div>
        </div>
      )}
      <Dialog
        open={!!slashDialog}
        onClose={() => setSlashDialog(null)}
        size="lg"
        title={
          slashDialog === "models" ? "AI models" :
          slashDialog === "mcp" ? "MCP servers" : "Personas"
        }
      >
        {/* Slash-created entities default to THIS chat's project — the narrowest
            scope the project-ownership model allows (personas/mcp are
            project-owned; models are company-wide so take no default). */}
        {slashDialog === "models" && <ModelsTab embedded canManage={isCompanyAdmin(role)} />}
        {slashDialog === "mcp" && <McpTab embedded defaultProjectId={pid} />}
        {slashDialog === "personas" && <PersonasTab embedded canManage={isCompanyAdmin(role)} defaultProjectId={pid} />}
      </Dialog>
      <ConfirmDialog
        open={confirmingEnd}
        onClose={() => setConfirmingEnd(false)}
        onConfirm={() => {
          setConfirmingEnd(false);
          setEndingSession(true);
          chat.send("@session close")
            .catch(() => undefined) // failure already toasted by send
            .finally(() => setEndingSession(false));
        }}
        title="End this session?"
        body={<p>Plain messages will stop routing to the persona automatically. You can open a new session anytime by mentioning them again.</p>}
        confirmLabel="End session"
        tone="neutral"
      />
      <TeamDialog pid={pid} projectName={project?.name ?? "This project"} canManage={isCompanyAdmin(role)} open={membersOpen} onClose={() => setMembersOpen(false)} />
    </div>
  );
}
