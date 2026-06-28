import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ServerCard } from "./ServerCard";
import { useServers } from "./use-servers";
import { useAuthStore } from "@/store/auth.store";
import { verifyServerAccess } from "@/services/auth.service";
import type { ServerEntry } from "@/types";
import { Plus } from "lucide-react";

export function ServerList() {
  const { servers, add, remove } = useServers();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const setServerUrl = useAuthStore((s) => s.setServerUrl);
  const navigate = useNavigate();

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect(server: ServerEntry) {
    if (!supabaseToken) {
      setError("You are not signed in.");
      return;
    }
    setError(null);
    setConnectingId(server.id);
    const cleanUrl = server.url.replace(/\/$/, "");
    const result = await verifyServerAccess(cleanUrl, supabaseToken);
    setConnectingId(null);

    if (result.ok) {
      setServerUrl(cleanUrl);
      navigate({ to: "/app" });
    } else if (result.status === 403) {
      setError("You don't have access to this server.");
    } else if (result.status === 0) {
      setError("Could not connect to server.");
    } else {
      setError(`Server returned ${result.status}.`);
    }
  }

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !url.trim()) return;
    add({ name: name.trim(), url: url.trim().replace(/\/$/, "") });
    setName("");
    setUrl("");
    setAdding(false);
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {servers.length === 0 && !adding && (
        <div className="rounded-lg border border-dashed border-border-strong p-8 text-center text-sm text-foreground-muted">
          No servers yet. Add your first NeuralOps server to get started.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {servers.map((s) => (
          <ServerCard
            key={s.id}
            server={s}
            onConnect={handleConnect}
            onRemove={remove}
            connecting={connectingId === s.id}
          />
        ))}
      </div>

      {adding ? (
        <form
          onSubmit={handleAdd}
          className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="server-name">Name</Label>
            <Input
              id="server-name"
              placeholder="Production"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="server-url">URL</Label>
            <Input
              id="server-url"
              placeholder="http://100.x.x.x:8000"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
            <Button type="submit">Add server</Button>
          </div>
        </form>
      ) : (
        <Button variant="outline" onClick={() => setAdding(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add server
        </Button>
      )}
    </div>
  );
}
