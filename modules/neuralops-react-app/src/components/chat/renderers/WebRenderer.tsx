// Note: X-Frame-Options blocking cannot be detected from client-side JS.
// We always show the iframe + an "Open in new tab" link as fallback.
export function WebRenderer({ content }: { content: string }) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border bg-muted px-3 py-1.5">
        <span className="truncate text-xs text-muted-foreground flex-1">{content}</span>
        <a
          href={content}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs text-primary hover:underline whitespace-nowrap"
        >
          Open in new tab ↗
        </a>
      </div>
      <iframe
        src={content}
        title="web preview"
        className="h-[400px] w-full"
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
    </div>
  );
}
