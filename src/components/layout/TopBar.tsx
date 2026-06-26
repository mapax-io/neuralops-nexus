import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  breadcrumb?: string;
}

export function TopBar({ breadcrumb }: Props) {
  return (
    <header className="flex h-12 items-center justify-between border-b border-[color:var(--border)] bg-[color:var(--background)] px-4">
      <div className="text-sm text-[color:var(--foreground-muted)]">
        {breadcrumb ?? "Workspace"}
      </div>
      <Button variant="ghost" size="icon" className="size-8">
        <Search className="size-4" />
      </Button>
    </header>
  );
}
