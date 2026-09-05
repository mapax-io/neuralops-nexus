"use client";

import { ChevronLeft, Hash, PanelRightClose, PanelRightOpen, Search, WifiOff } from "lucide-react";
import { MemberStack } from "@/components/shell/members-dialog";
import { ChatTabs, type ChatTab } from "./chat-tabs";

// Presentational chat header shared by the live TopicView and the /dev
// fixture — one source of truth so the fixture can't drift from the app.
export function ChatHeaderBar({
  title,
  projectName,
  channelName,
  connection = "connected",
  loading = false,
  onMembers,
  membersPid,
  searchOpen = false,
  onToggleSearch,
  searchShortcut,
  onBack,
  panelCollapsed = false,
  onTogglePanel,
  tab,
  onTab,
}: {
  title: string;
  projectName?: string;
  channelName?: string;
  connection?: string;
  loading?: boolean;
  onMembers?: () => void;
  membersPid?: string;
  searchOpen?: boolean;
  onToggleSearch?: () => void;
  searchShortcut?: string;
  // Phone-only: chats live in the right panel, which the open chat replaces
  // on small screens — this is the way back to the list.
  onBack?: () => void;
  // Desktop-only: collapse/expand the chats panel on the right.
  panelCollapsed?: boolean;
  onTogglePanel?: () => void;
  tab: ChatTab;
  onTab: (tab: ChatTab) => void;
}) {
  return (
    <header className="flex-none border-b border-line px-4">
      <div className="flex h-11 items-center gap-2">
        {onBack && (
          <button
            aria-label="Back to this channel's topics"
            title="Back to topics"
            onClick={onBack}
            className="-ml-1 flex size-7 flex-none items-center justify-center rounded-lg text-ink2 hover:bg-surface hover:text-ink lg:hidden"
          >
            <ChevronLeft size={17} strokeWidth={2} />
          </button>
        )}
        <h1 title={title} className="truncate text-[14.5px] font-semibold">{title}</h1>
        <span title={`${projectName ?? ""} / #${channelName ?? ""}`} className="flex items-center gap-1 truncate text-[12.5px] text-ink2">
          {projectName} / <Hash size={11} strokeWidth={2} /> {channelName}
        </span>
        <span className="flex-1" />
        {!loading && connection !== "connected" && (
          <span className="flex items-center gap-1.5 rounded-full border border-warn/40 bg-warn/10 px-2.5 py-0.5 text-[11.5px] font-medium text-warn" role="status">
            <WifiOff size={12} strokeWidth={2} />
            {connection === "connecting" ? "Reconnecting…" : "Live updates offline"}
          </span>
        )}
        {onMembers && <MemberStack onClick={onMembers} pid={membersPid} />}
        {onToggleSearch && (
          <button
            aria-label="Search this chat"
            title={searchShortcut ? `Search this chat (workspace-wide: ${searchShortcut})` : "Search this chat"}
            aria-pressed={searchOpen}
            onClick={onToggleSearch}
            className={`flex size-7 items-center justify-center rounded-lg transition-colors ${searchOpen ? "bg-accent/10 text-accent" : "text-ink2 hover:bg-surface hover:text-ink"}`}
          >
            <Search size={14} strokeWidth={2} />
          </button>
        )}
        {onTogglePanel && (
          <button
            aria-label={panelCollapsed ? "Show the topics panel" : "Hide the topics panel"}
            title={panelCollapsed ? "Show topics" : "Hide topics"}
            aria-pressed={!panelCollapsed}
            onClick={onTogglePanel}
            className="hidden size-7 items-center justify-center rounded-lg text-ink2 transition-colors hover:bg-surface hover:text-ink lg:flex"
          >
            {panelCollapsed ? <PanelRightOpen size={14} strokeWidth={2} /> : <PanelRightClose size={14} strokeWidth={2} />}
          </button>
        )}
      </div>
      <ChatTabs tab={tab} onTab={onTab} />
    </header>
  );
}
