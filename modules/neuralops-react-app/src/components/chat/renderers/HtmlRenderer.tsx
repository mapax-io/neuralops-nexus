/**
 * HtmlRenderer — renders AI-generated self-contained HTML in a sandboxed iframe.
 *
 * Used for output types: chart, table, diagram, form, html.
 * The AI produces a complete <!DOCTYPE html>...</html> page which runs
 * in isolation (no same-origin, scripts allowed for CDN imports like Chart.js).
 *
 * Security:
 *   sandbox="allow-scripts"  → JS runs but cannot access parent origin
 *   No allow-same-origin     → iframe cannot read parent cookies/storage
 *   No allow-forms           → form submissions blocked (forms submit internally via JS)
 *   No allow-popups          → can't open new windows
 */

import { useEffect, useRef, useState } from "react";
import { Maximize2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

const DEFAULT_HEIGHT = 360;
const EXPANDED_HEIGHT = 600;

export function HtmlRenderer({ content }: { content: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [key, setKey] = useState(0); // increment to force iframe reload

  const height = expanded ? EXPANDED_HEIGHT : DEFAULT_HEIGHT;

  // Re-set srcdoc when content changes (handles streaming → done transition)
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    // srcdoc assignment re-renders the iframe content
    iframe.srcdoc = content || "<html><body></body></html>";
  }, [content]);

  function handleReload() {
    setKey((k) => k + 1);
  }

  if (!content) {
    return (
      <div className="flex h-20 items-center justify-center rounded-md border border-border bg-card text-sm text-muted-foreground">
        No content
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border bg-card">
      {/* Toolbar */}
      <div
        className="flex items-center justify-between border-b px-3 py-1.5"
        style={{
          backgroundColor: "var(--code-header-bg)",
          borderColor: "var(--code-border)",
        }}
      >
        <span className="text-xs font-medium text-muted-foreground">
          Interactive output
        </span>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
            onClick={handleReload}
            title="Reload"
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((e) => !e)}
            title={expanded ? "Collapse" : "Expand"}
          >
            <Maximize2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Sandboxed iframe */}
      <iframe
        key={key}
        ref={iframeRef}
        srcDoc={content}
        title="AI output"
        className="w-full border-0 bg-white"
        style={{ height }}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
