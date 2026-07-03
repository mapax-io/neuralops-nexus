import { useState } from "react";
import { TopicList } from "./TopicList";
import { MessageList } from "./MessageList";
import { MessageInput } from "./MessageInput";
import { TypingIndicator } from "./TypingIndicator";
import { useUIStore } from "@/store/ui.store";
import { useSendMessage } from "@/hooks/useChat";
import type { TypingActor } from "./types";

export function ChatArea() {
  const activeProjectId = useUIStore((s) => s.activeProjectId);
  const activeChannelId = useUIStore((s) => s.activeChannelId);
  const activeTopicId = useUIStore((s) => s.activeTopicId);
  const setActiveTopicId = useUIStore((s) => s.setActiveTopicId);
  const sendMessageMutation = useSendMessage();
  const [typing] = useState<TypingActor[]>([]);

  if (!activeProjectId || !activeChannelId) return null;

  async function handleSend(text: string) {
    if (!activeProjectId || !activeChannelId) return;
    try {
      const res = await sendMessageMutation.mutateAsync({
        content: text,
        channel_id: activeChannelId,
        project_id: activeProjectId,
        topic_id: activeTopicId ?? undefined,
      });
      if (!activeTopicId && res?.topic_id) {
        setActiveTopicId(res.topic_id);
      }
    } catch {
      /* toast handled in hook */
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      <TopicList projectId={activeProjectId} channelId={activeChannelId} />
      {/* Right column: must be overflow-hidden so the flex children are constrained */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
        {/* MessageList wrapper: min-h-0 allows flex shrink, overflow-hidden contains scroll */}
        <div className="min-h-0 flex-1 overflow-hidden">
          <MessageList />
        </div>
        <TypingIndicator actors={typing} />
        <MessageInput
          onSend={handleSend}
          projectId={activeProjectId}
          topicId={activeTopicId}
        />
      </div>
    </div>
  );
}
