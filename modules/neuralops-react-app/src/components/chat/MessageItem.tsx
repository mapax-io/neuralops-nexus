import type { ChatMessage, MessageRenderType } from "./types";
import { TextRenderer } from "./renderers/TextRenderer";
import { CodeRenderer } from "./renderers/CodeRenderer";
import { HtmlRenderer } from "./renderers/HtmlRenderer";
import { TerminalRenderer } from "./renderers/TerminalRenderer";
import { ImageRenderer } from "./renderers/ImageRenderer";
import { WebRenderer } from "./renderers/WebRenderer";

function formatTime(ts: string): { short: string; full: string } {
  try {
    const date = new Date(ts);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const isThisWeek =
      now.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000;

    const time = date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    let short: string;
    if (isToday) {
      short = time;
    } else if (isThisWeek) {
      const day = date.toLocaleDateString([], { weekday: "short" });
      short = `${day} ${time}`;
    } else {
      const dateStr = date.toLocaleDateString([], {
        month: "short",
        day: "numeric",
      });
      short = `${dateStr}, ${time}`;
    }

    const full = date.toLocaleString([], {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    return { short, full };
  } catch {
    return { short: "", full: "" };
  }
}

export function MessageItem({ message }: { message: ChatMessage }) {
  const isHuman = message.sender.type === "human";
  const initial = message.sender.name.slice(0, 1).toUpperCase();

  return (
    <div className="flex gap-3 px-4 py-2 hover:bg-muted/30">
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isHuman
            ? "bg-primary-tint text-primary"
            : "bg-accent text-accent-foreground"
        }`}
      >
        {message.sender.avatar ? (
          <img
            src={message.sender.avatar}
            alt={message.sender.name}
            className="h-full w-full rounded-full object-cover"
          />
        ) : (
          initial
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-foreground">
            {message.sender.name}
          </span>
          {(() => {
            const { short, full } = formatTime(message.timestamp);
            return (
              <span
                className="text-xs text-muted-foreground cursor-default"
                title={full}
              >
                {short}
              </span>
            );
          })()}
        </div>
        <div className="mt-1">
          <Renderer message={message} />
          {message.isStreaming && (
            <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-foreground align-middle" />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Renderer — delegates to the correct renderer based on message.type (render_as).
 *
 * Renderer selection:
 *   "html"     → HtmlRenderer (sandboxed iframe — for chart, table, diagram, form, html)
 *   "code"     → CodeRenderer (syntax-highlighted)
 *   "terminal" → TerminalRenderer (monospace pre)
 *   "image"    → ImageRenderer
 *   "web"      → WebRenderer (URL iframe)
 *   "text" | * → TextRenderer (markdown)
 */
function Renderer({ message }: { message: ChatMessage }) {
  const type: MessageRenderType = message.type ?? "text";

  switch (type) {
    case "html":
      return <HtmlRenderer content={message.content} />;

    case "code":
      return (
        <CodeRenderer content={message.content} language={message.language} />
      );

    case "terminal":
      return <TerminalRenderer content={message.content} />;

    case "image":
      return <ImageRenderer content={message.content} />;

    case "web":
      return <WebRenderer content={message.content} />;

    case "text":
    default:
      return <TextRenderer content={message.content} />;
  }
}
