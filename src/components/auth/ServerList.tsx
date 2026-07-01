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
import { Plus, Server } from "lucide-react";

export function ServerList() {
  const { servers, add, remove, touch } = useServers();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const setServerInfo = useAuthStore((s) => s.setServerInfo);
  const navigate = useNavigate();

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [connectedId, setConnectedId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function handleConnect(server: ServerEntry) {
    if (!supabaseToken) {
      setErrors({ [server.id]: "You are not signed in." });
      return;
    }
    setErrors((e) => ({ ...e, [server.id]: "" }));
    setConnectingId(server.id);
    const cleanUrl = server.url.replace(/\/$/, "");
    const result = await verifyServerAccess(cleanUrl, supabaseToken);
    setConnectingId(null);

    if (result.ok) {
      touch(server.id);
      setConnectedId(server.id);
      setServerInfo({
        serverUrl: cleanUrl,
        userId: result.userId,
        role: result.role,
        companyName: result.companyName,
        isOwner: result.isOwner,
      });
      setTimeout(() => navigate({ to: "/app" }), 500);
    } else {
      const msg =
        result.status === 403
          ? "You don't have access to this server."
          : result.status === 0
            ? "Could not connect to server."
            : `Server returned ${result.status}.`;
      setErrors((e) => ({ ...e, [server.id]: msg }));
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
      {servers.length === 0 && !adding && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border-strong bg-card p-10 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Server className="h-6 w-6" />
          </div>
          <div className="text-sm font-medium text-foreground">
            No servers connected yet
          </div>
          <p className="max-w-sm text-xs text-foreground-muted">
            Add your NeuralOps backend URL to get started. This is usually your
            local IP or Tailscale address.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {servers.map((s) => (
          <ServerCard
            key={s.id}
            server={s}
            onConnect={handleConnect}
            onRemove={(id) => {
              remove(id);
              setErrors((e) => {
                const next = { ...e };
                delete next[id];
                return next;
              });
            }}
            connecting={connectingId === s.id}
            connected={connectedId === s.id}
            error={errors[s.id] || null}
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
              placeholder="e.g. My Mac, Home Server, Office"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="server-url">URL</Label>
            <Input
              id="server-url"
              placeholder="e.g. http://192.168.1.90:8003 or http://100.x.x.x:8003"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <p className="text-xs text-foreground-muted">
              This is the address of your NeuralOps Django backend
            </p>
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
