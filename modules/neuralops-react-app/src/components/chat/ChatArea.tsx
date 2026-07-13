import { TopicList } from "./TopicList";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { TypingIndicator } from "./TypingIndicator";
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

  if (!activeProjectId || !activeChannelId) return null;

  return (
    <div className="flex h-full overflow-hidden">
      <TopicList projectId={activeProjectId} channelId={activeChannelId} />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
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
          placeholder={activeTopicId ? undefined : "Select a conversation to start messaging"}
        />
      </div>
    </div>
  );
}
