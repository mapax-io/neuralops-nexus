import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import { Button } from "@/components/ui/button";

export function CodeRenderer({
  content,
  language,
}: {
  content: string;
  language?: string;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);

  async function handleCopy() {
    await navigator.clipboard.writeText(content);
    setCopied(true);
  }

  const md = `\`\`\`${language ?? ""}\n${content}\n\`\`\``;

  return (
    <div
      className="relative overflow-hidden rounded-md border"
      style={{ backgroundColor: "var(--code-bg)", borderColor: "var(--code-border)" }}
    >
      <div
        className="flex items-center justify-between border-b px-3 py-1.5"
        style={{ backgroundColor: "var(--code-header-bg)", borderColor: "var(--code-border)" }}
      >
        <span className="text-xs font-medium text-muted-foreground">
          {language ?? "code"}
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
      <div
        className="overflow-x-auto text-sm [&_pre]:!m-0 [&_pre]:!bg-transparent [&_pre]:p-4"
        style={{ color: "var(--code-text)" }}
      >
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{md}</ReactMarkdown>
      </div>
    </div>
  );
}
