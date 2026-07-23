export interface MessageSender {
  id: string;
  name: string;
  type: "human" | "persona" | "agent";
  avatar: string | null;
}

/**
 * render_as → type mapping used by MessageItem:
 *   "text"     → TextRenderer   (markdown)
 *   "code"     → CodeRenderer   (syntax-highlighted block)
 *   "html"     → HtmlRenderer   (sandboxed iframe — chart, table, diagram, form, html)
 *   "terminal" → TerminalRenderer (monospace pre with $ styling)
 *   "image"    → ImageRenderer
 *   "web"      → WebRenderer    (URL in iframe)
 */
export type MessageRenderType =
  | "text"
  | "code"
  | "html"
  | "terminal"
  | "image"
  | "web";

export interface ChatMessage {
  id: string;
  type: MessageRenderType;
  message_type?: string;
  output_type?: string;           // M7: semantic type ("chart", "diagram", "table", etc.)
  content: string;
  language?: string;
  metadata?: Record<string, unknown>;
  sender: MessageSender;
  timestamp: string;
  isStreaming?: boolean;
}

export interface TypingActor {
  id: string;
  name: string;
  type: "human" | "persona" | "agent";
  avatar: string | null;
}
