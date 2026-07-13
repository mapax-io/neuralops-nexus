import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import "highlight.js/styles/github-dark.css";
import React from "react";

// ---------------------------------------------------------------------------
// Inline code — small monospace chip
// ---------------------------------------------------------------------------
function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-muted px-1 py-0.5 text-sm font-mono text-foreground">
      {children}
    </code>
  );
}

// ---------------------------------------------------------------------------
// Block code — styled container that matches CodeRenderer, with copy button.
// The `pre` ref lets us grab plain innerText for the clipboard (works even
// when rehype-highlight has wrapped the content in <span> elements).
// ---------------------------------------------------------------------------
function BlockCode({
  children,
  ...props
}: React.ComponentPropsWithoutRef<"pre">) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  // Extract language from the className of the child <code> element.
  // rehype-highlight adds "language-<lang> hljs" so we strip both.
  const codeEl = React.Children.toArray(children).find(
    (c): c is React.ReactElement =>
      React.isValidElement(c) && (c as React.ReactElement).type === "code",
  ) as React.ReactElement<{ className?: string }> | undefined;
  const rawClass = codeEl?.props?.className ?? "";
  const language =
    rawClass
      .split(" ")
      .find((cls: string) => cls.startsWith("language-"))
      ?.replace("language-", "") ?? "code";

  async function handleCopy() {
    const text = preRef.current?.innerText ?? "";
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      className="relative my-2 overflow-hidden rounded-md border"
      style={{
        backgroundColor: "var(--code-bg)",
        borderColor: "var(--code-border)",
      }}
    >
      {/* Header bar */}
      <div
        className="flex items-center justify-between border-b px-3 py-1.5"
        style={{
          backgroundColor: "var(--code-header-bg)",
          borderColor: "var(--code-border)",
        }}
      >
        <span className="text-xs font-medium text-muted-foreground">
          {language}
        </span>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-muted-foreground hover:text-foreground"
          onClick={handleCopy}
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" /> Copy
            </>
          )}
        </Button>
      </div>

      {/* Code body */}
      <pre
        ref={preRef}
        {...props}
        className="overflow-x-auto text-sm [&]:!m-0 [&]:!bg-transparent [&]:p-4"
      >
        {children}
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TextRenderer — renders markdown with GFM + syntax-highlighted code blocks
// ---------------------------------------------------------------------------
export function TextRenderer({ content }: { content: string }) {
  return (
    <div
      className={[
        "prose prose-sm max-w-none text-foreground",
        // Links
        "[&_a]:text-primary [&_a]:underline",
        // Headings
        "[&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm",
        // Lists
        "[&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5",
        // Blockquote
        "[&_blockquote]:border-l-2 [&_blockquote]:border-muted-foreground/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_blockquote]:italic",
        // Tables (GFM)
        "[&_table]:text-sm [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1",
        // Reset prose's default background on code so our custom components control it
        "[&_pre]:!bg-transparent [&_pre]:!p-0 [&_pre]:!m-0",
      ].join(" ")}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Block code goes through our styled BlockCode
          pre: BlockCode,
          // Inline code uses the chip style
          code: ({ children, className }) => {
            // When code is inside a pre, BlockCode already wraps it —
            // className will contain "language-*". Inline code has no className.
            if (className) {
              // This is the inner <code> of a fenced block; BlockCode renders it
              return <code className={className}>{children}</code>;
            }
            return <InlineCode>{children}</InlineCode>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
