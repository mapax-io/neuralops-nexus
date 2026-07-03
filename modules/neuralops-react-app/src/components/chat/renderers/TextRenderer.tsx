import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function TextRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none text-foreground [&_a]:text-primary [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
