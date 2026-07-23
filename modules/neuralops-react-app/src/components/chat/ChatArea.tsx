import { useState } from "react";
import { Layers } from "lucide-react";
import { TopicList } from "./TopicList";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { TypingIndicator } from "./TypingIndicator";
import { ContextPanel } from "./ContextPanel";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/store/ui.store";
import { useTopicMessages } from "@/hooks/useChat";

export function ChatArea() {
  const activeProjectId = useUIStore((s) => s.activeProjectId);
  const activeChannelId = useUIStore((s) => s.activeChannelId);
  const activeTopicId = useUIStore((s) => s.activeTopicId);

  const { messages, loading, send } = useTopicMessages(
    activeProjectId,
    activeChannelId,
    activeTopicId,
  );

  const [panelOpen, setPanelOpen] = useState(false);

  if (!activeProjectId || !activeChannelId) return null;

  return (
    <div className="flex h-full overflow-hidden">
      <TopicList projectId={activeProjectId} channelId={activeChannelId} />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
        {/* Top bar */}
        <div className="flex items-center justify-end border-b px-3 py-1.5">
          <Button
            variant={panelOpen ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={() => setPanelOpen((v) => !v)}
            disabled={!activeTopicId}
            title="Toggle context panel"
          >
            <Layers className="h-3.5 w-3.5" />
            Context
          </Button>
        </div>

        {/* Main area: messages + optional context panel */}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <div className="min-h-0 flex-1 overflow-hidden">
              {loading ? (
                <div className="flex h-full items-center justify-center">
                  <p className="text-sm text-muted-foreground">Loading messages…</p>
                </div>
              ) : (
                <MessageList messages={messages} />
              )}
            </div>

            <TypingIndicator actors={[]} />

            <MessageInput
              onSend={send}
              projectId={activeProjectId}
              topicId={activeTopicId}
              disabled={!activeTopicId}
              placeholder={
                activeTopicId ? undefined : "Select a conversation to start messaging"
              }
            />
          </div>

          {/* Context panel sidebar */}
          <ContextPanel
            open={panelOpen}
            onClose={() => setPanelOpen(false)}
            projectId={activeProjectId}
            topicId={activeTopicId}
          />
        </div>
      </div>
    </div>
  );
}
