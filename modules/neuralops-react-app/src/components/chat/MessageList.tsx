import { useEffect, useRef } from "react";
import { MessageItem } from "./MessageItem";
import type { ChatMessage } from "./types";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Track total streamed content length so we scroll on every delta,
  // not just when a new message is added.
  const streamingLength = messages.reduce(
    (acc, m) => acc + (m.isStreaming ? m.content.length : 0),
    0,
  );

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, streamingLength]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-sm text-muted-foreground">
          No messages yet. Start the conversation below.
        </p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto py-4">
      {messages.map((m) =>
        m.message_type === "system" ? (
          <div
            key={m.id}
            className="flex items-center gap-2 px-6 py-1 text-xs text-muted-foreground"
          >
            <div className="h-px flex-1 bg-border" />
            <span>{m.content}</span>
            <div className="h-px flex-1 bg-border" />
          </div>
        ) : (
          <MessageItem key={m.id} message={m} />
        )
      )}
    </div>
  );
}
