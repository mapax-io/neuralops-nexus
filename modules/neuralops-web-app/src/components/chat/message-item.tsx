"use client";

import { useRouter } from "next/navigation";
import { useUiStore } from "@/stores/ui.store";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Plug2, Copy } from "lucide-react";
import { toast } from "sonner";
import { absolutizeMedia } from "@/lib/api/client";
import { copyText } from "@/lib/browser";
import { RICH_OUTPUT_TYPES, stripLeakedMarkers } from "@/lib/composer/directives";
import type { UiMessage } from "@/lib/realtime/message-store";
import { HtmlFrame } from "./html-frame";
import { MermaidBlock } from "./mermaid-block";

// Slack-style: the inline stamp is time-of-day only — the day divider above
// the group carries the date. Full timestamp stays on hover via title.
function formatTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// Centered pill, Slack-style — no full-width rules flanking the text. The
// time-of-day is appended (session opened/closed events are worth timestamping);
// the full timestamp stays on hover via title.
export const SystemSeparator = memo(function SystemSeparator({
  content,
  createdAt,
}: {
  content: string;
  createdAt?: string | null;
}) {
  const time = formatTime(createdAt ?? null);
  const title = time && createdAt ? `${content} · ${new Date(createdAt).toLocaleString()}` : content;
  return (
    <div className="my-2.5 flex justify-center px-4" role="status">
      <span title={title} className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface2/70 px-3.5 py-1 text-[11.5px] text-ink2">
        <span className="min-w-0 truncate">{content}</span>
        {time && <span className="shrink-0 tabular-nums text-ink2/70">· {time}</span>}
      </span>
    </div>
  );
});

// In-bubble "Thinking …" cue for a persona whose stream hasn't produced a token
// yet — mirrors the human typing style (bouncing dots), but lives in the message
// so it can't overlap anything.
function ThinkingDots() {
  return (
    <span className="mt-1 inline-flex items-center gap-1.5 text-[13px] italic text-ink2" role="status" aria-label="Thinking">
      Thinking
      <span className="flex gap-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-1 animate-bounce rounded-full bg-live" style={{ animationDelay: `${i * 150}ms` }} />
        ))}
      </span>
    </span>
  );
}

function CodeBlock({ content, terminal }: { content: string; terminal?: boolean }) {
  return (
    <div className="mt-1 overflow-hidden rounded-xl border border-line">
      <div className="flex items-center justify-between border-b border-line bg-surface2 px-3 py-1.5">
        <span className="font-mono text-[11px] text-ink2">{terminal ? "terminal" : "code"}</span>
        <button
          aria-label="Copy to clipboard"
          className="flex items-center gap-1.5 text-[11.5px] text-ink2 hover:text-ink"
          onClick={() => void copyText(content).then((ok) => (ok ? toast.success("Copied") : toast.error("Copy failed — check clipboard permissions")))}
        >
          <Copy size={12} strokeWidth={2} /> Copy
        </button>
      </div>
      <pre className="overflow-x-auto bg-[#0d1526] p-3.5 font-mono text-[12.5px] leading-relaxed text-[#dde7f5]">
        {terminal
          ? content.split("\n").map((line, i) => (
              <span key={i} className={line.trimStart().startsWith("$") ? "text-[#3fb950]" : undefined}>
                {line}
                {"\n"}
              </span>
            ))
          : content}
      </pre>
    </div>
  );
}

// Text of a hast subtree — what a fenced block's <code> actually contains.
type HastNode = { type?: string; value?: string; tagName?: string; properties?: { className?: unknown }; children?: HastNode[] };
const hastText = (n: HastNode | undefined): string =>
  !n ? "" : n.type === "text" ? (n.value ?? "") : (n.children ?? []).map(hastText).join("");

// A fenced block inside a markdown reply, in the same chrome as the dedicated
// code output: a slim header with the language and a Copy button, then the
// code. A header (not an overlay) so the button never covers a long first
// line when the block scrolls sideways on a phone, and stays reachable on touch.
function FencedCode({ lang, code, children }: { lang: string | null; code: string; children: React.ReactNode }) {
  return (
    <div className="my-2 overflow-hidden rounded-lg border border-line [&>pre]:my-0 [&>pre]:rounded-none">
      <div className="flex items-center justify-between border-b border-line bg-surface2 px-3 py-1">
        <span className="font-mono text-[11px] text-ink2">{lang ?? "code"}</span>
        <button
          type="button"
          aria-label="Copy code"
          title="Copy code"
          onClick={() => void copyText(code).then((ok) => (ok ? toast.success("Copied") : toast.error("Copy failed — check clipboard permissions")))}
          className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-ink2 hover:text-ink"
        >
          <Copy size={12} strokeWidth={2} /> Copy
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function ComposingPlaceholder({ outputType }: { outputType: string }) {
  return (
    <div className="mt-1 flex items-center gap-3 rounded-xl border border-line bg-surface2/60 px-4 py-3.5">
      <span aria-hidden className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-1.5 animate-bounce rounded-full bg-accent" style={{ animationDelay: `${i * 150}ms` }} />
        ))}
      </span>
      <span className="text-[13px] text-ink2">Composing {outputType === "html" ? "a page" : outputType === "terminal" ? "terminal output" : `a ${outputType}`}…</span>
    </div>
  );
}

function Body({ message }: { message: UiMessage }) {
  // Rich outputs stream raw markers/HTML — show a composing placeholder
  // until message_done delivers the parsed result (streaming display policy).
  if (message.isStreaming && RICH_OUTPUT_TYPES.has(message.outputType)) {
    return <ComposingPlaceholder outputType={message.outputType} />;
  }
  const content = stripLeakedMarkers(message.content);
  if (message.renderAs === "html") {
    return <HtmlFrame content={content} title={`Interactive output from ${message.senderName ?? "a persona"}`} />;
  }
  if (message.renderAs === "code") return <CodeBlock content={content} />;
  if (message.renderAs === "terminal") return <CodeBlock content={content} terminal />;
  if (message.renderAs === "image") {
    const src = content.trim();
    return (
      <a href={src} target="_blank" rel="noopener noreferrer" title="Open full size">
        {/* eslint-disable-next-line @next/next/no-img-element -- runtime URL from the AI, domain unknown at build */}
        <img src={src} alt="Generated image" className="max-h-[300px] rounded-lg border border-line" />
      </a>
    );
  }
  if (message.renderAs === "web") {
    const url = content.trim();
    return (
      <div className="overflow-hidden rounded-lg border border-line">
        <div className="flex items-center gap-2 border-b border-line bg-surface2 px-3 py-1.5">
          <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink2">{url}</span>
          <a href={url} target="_blank" rel="noopener noreferrer" className="flex-none text-[11.5px] text-accent hover:underline">Open ↗</a>
        </div>
        {/* Some sites refuse framing (X-Frame-Options) — undetectable here; the Open link is the fallback. */}
        <iframe src={url} sandbox="allow-scripts allow-same-origin" referrerPolicy="no-referrer" title="Web preview" className="h-[400px] w-full bg-white" />
      </div>
    );
  }
  // Default text: markdown WITHOUT raw-HTML execution (security invariant —
  // react-markdown escapes embedded HTML unless rehype-raw is added; it never is).
  return (
    <div className="max-w-none break-words text-[14px] leading-relaxed [overflow-wrap:anywhere] [&_a]:break-all [&_a]:text-accent [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-3 [&_blockquote]:text-ink2 [&_code]:rounded [&_code]:bg-surface2 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[12.5px] [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-surface2 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:px-0 [&_pre_code]:py-0 [&_table]:my-2 [&_table]:border-collapse [&_td]:border [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-line [&_th]:bg-surface2 [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:pl-5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a(props) {
            const { href, children } = props as { href?: string; children?: React.ReactNode };
            const external = /^https?:\/\//.test(href ?? "");
            return (
              <a href={href} target={external ? "_blank" : undefined} rel={external ? "noopener noreferrer" : undefined}>
                {children}
              </a>
            );
          },
          code(props) {
            const { className, children } = props as { className?: string; children?: React.ReactNode };
            const isMermaid = /language-mermaid/.test(className ?? "");
            if (isMermaid && !message.isStreaming) return <MermaidBlock source={String(children ?? "")} />;
            return <code className={className}>{children}</code>;
          },
          pre(props) {
            // A rendered mermaid diagram must not sit inside the markdown
            // <pre> chrome (grey code box) — unwrap it.
            const { node, children } = props as { node?: HastNode; children?: React.ReactNode };
            const codeNode = node?.children?.find((c) => c.tagName === "code");
            const cls = codeNode?.properties?.className;
            if (Array.isArray(cls) && cls.includes("language-mermaid") && !message.isStreaming) return <>{children}</>;
            const lang = Array.isArray(cls) ? (cls.find((c) => typeof c === "string" && c.startsWith("language-")) as string | undefined)?.slice(9) ?? null : null;
            // Fenced text ends with the closing fence's newline — not part of the snippet.
            return <FencedCode lang={lang} code={hastText(codeNode).replace(/\n$/, "")}>{children}</FencedCode>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export const MessageItem = memo(function MessageItem({ message }: { message: UiMessage }) {
  if (message.isSystem) return <SystemSeparator content={message.content} createdAt={message.createdAt} />;
  const isPersona = message.senderType !== "human";
  const avatar = absolutizeMedia(message.senderAvatar);
  return (
    <article data-msg-id={message.id} className="group relative flex gap-3 rounded-lg px-4 py-1.5 hover:bg-surface2/40">
      {/* Slack-style hover actions — only what the server actually supports. */}
      {!message.isStreaming && (
        <div className="absolute -top-3 right-4 z-10 flex overflow-hidden rounded-lg border border-line bg-surface shadow-md opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-within:opacity-100">
          <button
            aria-label="Copy message"
            title="Copy message"
            onClick={() => void copyText(stripLeakedMarkers(message.content)).then((ok) => (ok ? toast.success("Message copied") : toast.error("Copy failed — check clipboard permissions")))}
            className="flex size-8 items-center justify-center text-ink2 hover:bg-surface2 hover:text-ink"
          >
            <Copy size={14} strokeWidth={2} />
          </button>
        </div>
      )}
      <span className={`mt-0.5 flex size-8 flex-none items-center justify-center overflow-hidden rounded-full text-[12px] font-bold text-white ${isPersona ? "bg-accent" : "bg-gradient-to-br from-stone-500 to-stone-700"}`}>
        {avatar ? (
          // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
          <img src={avatar} alt="" className="size-full object-cover" />
        ) : (
          (message.senderName ?? "?")[0]?.toUpperCase()
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2 text-[12.5px] text-ink2">
          <b className="text-[13px] font-semibold text-ink">{isPersona ? `@${message.senderName ?? "persona"}` : message.senderName ?? "someone"}</b>
          {isPersona && <span className="rounded-full border border-accent/30 bg-accent/10 px-1.5 text-[10px] font-semibold text-accent">persona</span>}
          <time title={message.createdAt ? new Date(message.createdAt).toLocaleString() : undefined}>{formatTime(message.createdAt)}</time>
        </p>
        {message.isError ? (
          <ErrorBubble content={message.content} />
        ) : (
          <Body message={message} />
        )}
        {message.isStreaming && !message.isStalled && (
          // Before the first token lands (plain path), show a "Thinking …" cue
          // like the human typing style — in-bubble, so nothing overlaps. Once
          // content streams (or for rich outputs with their own placeholder),
          // fall back to the caret.
          !message.content.trim() && !RICH_OUTPUT_TYPES.has(message.outputType) ? (
            <ThinkingDots />
          ) : (
            <span aria-label="generating" className="mt-1 inline-block h-[15px] w-[7px] animate-pulse bg-accent align-middle" />
          )
        )}
        {message.isStalled && (
          <p className="mt-1 text-[12px] text-warn">This response has gone quiet — it may have failed on the server. Mention the persona again to retry.</p>
        )}
      </div>
    </article>
  );
}, (prev, next) => prev.message === next.message);

// Error bubble — for an MCP OAuth-token expiry the backend forwards the
// "needs to be reconnected" sentence verbatim; we detect it and offer a
// one-click jump to the MCP servers screen. useRouter lives HERE so ordinary
// messages never require a router context.
function ErrorBubble({ content }: { content: string }) {
  const router = useRouter();
  const needsReauth = /reconnect/i.test(content) && /mcp/i.test(content);
  return (
    <div className="text-[14px] text-crit">
      <p>{content || "Something went wrong generating this response."}</p>
      {needsReauth && (
        <button
          onClick={() => { useUiStore.getState().setIntelSection("mcp"); router.push("/intelligence"); }}
          className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-crit/30 bg-crit/5 px-2 py-0.5 text-[12px] font-medium text-crit transition-colors hover:bg-crit/10"
        >
          <Plug2 size={12} strokeWidth={2} /> Reconnect in MCP servers
        </button>
      )}
    </div>
  );
}
