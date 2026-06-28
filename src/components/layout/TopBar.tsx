import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  breadcrumb?: string[];
}

export function TopBar({ breadcrumb = [] }: Props) {
  return (
    <header
      className="flex h-12 items-center justify-between border-b border-border bg-background px-4"
      data-component="TopBar"
    >
      <nav className="flex items-center gap-2 text-sm text-foreground-muted">
        {breadcrumb.length === 0 ? (
          <span>Workspace</span>
        ) : (
          breadcrumb.map((seg, i) => (
            <span key={i} className="flex items-center gap-2">
              {i > 0 && <span className="text-foreground-muted">/</span>}
              <span
                className={
                  i === breadcrumb.length - 1
                    ? "text-foreground font-medium"
                    : ""
                }
              >
                {seg}
              </span>
            </span>
          ))
        )}
      </nav>
      <Button size="icon" variant="ghost" aria-label="Search">
        <Search className="h-4 w-4" />
      </Button>
    </header>
  );
}
