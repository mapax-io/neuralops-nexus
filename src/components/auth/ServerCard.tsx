import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Server, Trash2 } from "lucide-react";
import type { ServerEntry } from "@/types";

interface Props {
  server: ServerEntry;
  onConnect: (server: ServerEntry) => void;
  onRemove: (id: string) => void;
  connecting?: boolean;
}

export function ServerCard({ server, onConnect, onRemove, connecting }: Props) {
  return (
    <Card className="flex items-center justify-between gap-4 p-4">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-tint text-primary">
          <Server className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate font-medium">{server.name}</div>
          <div className="truncate text-xs text-foreground-muted">{server.url}</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => onConnect(server)}
          disabled={connecting}
        >
          {connecting ? "Connecting…" : "Connect"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onRemove(server.id)}
          aria-label="Remove server"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  );
}
