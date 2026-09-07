"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Copy, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import type { ServerConfig } from "@/lib/api/servers";
import { copyText } from "@/lib/browser";
import { Skeleton } from "@/components/ui/surfaces";
import { compareServerVersion } from "@/lib/version";
import type { SavedServer } from "@/stores/servers.store";

// Deterministic identity for each server: a monogram tile with a stable
// gradient — a server is a place you enter, not a config row.
const TILE_GRADIENTS = [
  "from-sky-500 to-blue-600",
  "from-cyan-500 to-sky-600",
  "from-blue-500 to-indigo-600",
  "from-emerald-500 to-teal-600",
  "from-amber-500 to-orange-600",
  "from-rose-500 to-pink-600",
];

export function tileGradient(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TILE_GRADIENTS[h % TILE_GRADIENTS.length];
}

function monogram(name: string): string {
  // Letters/digits only — prefixes like "[demo]" must not leak into the tile.
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
}

function relativeTime(iso?: string): string | null {
  if (!iso) return null;
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export interface ChooserEntry {
  server: SavedServer;
  config: ServerConfig | null | undefined;
  checking: boolean;
  connecting: boolean;
  error?: string;
}

const SEARCH_THRESHOLD = 6;

export function ServerChooser({ entries, onConnect, onRemove, onAdd, loading }: {
  entries: ChooserEntry[];
  onConnect: (server: SavedServer) => void;
  onRemove: (server: SavedServer) => void;
  onAdd: () => void;
  // First account sync still in flight — show placeholder rows, never the
  // empty state (an "Add your server" that pops into a list is a lie).
  loading?: boolean;
}) {
  const [query, setQuery] = useState("");

  // Most-recently-used first — the server you use daily is always on top.
  const sorted = useMemo(
    () =>
      [...entries].sort((a, b) => {
        const la = a.server.lastConnected ?? "";
        const lb = b.server.lastConnected ?? "";
        return lb.localeCompare(la) || a.server.name.localeCompare(b.server.name);
      }),
    [entries],
  );
  const q = query.trim().toLowerCase();
  const visible = q ? sorted.filter((e) => e.server.name.toLowerCase().includes(q) || e.server.url.toLowerCase().includes(q)) : sorted;
  const searchable = entries.length >= SEARCH_THRESHOLD;

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_24px_70px_-32px_rgba(0,0,0,.5)]">
      {searchable && (
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-2.5">
          <Search size={15} strokeWidth={2} className="flex-none text-ink2" />
          <input
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Filter ${entries.length} servers…`}
            aria-label="Filter servers"
            className="w-full bg-transparent text-[13.5px] outline-none placeholder:text-ink2/60"
          />
        </div>
      )}
      <div className={searchable ? "max-h-[56vh] overflow-y-auto" : ""}>
      {loading && entries.length === 0 && (
        <div className="flex flex-col" role="status" aria-label="Loading your servers">
          {[0, 1].map((i) => (
            <div key={i} className={`flex items-center gap-4 px-5 py-4 ${i > 0 ? "border-t border-line" : ""}`}>
              <Skeleton className="size-11 rounded-xl" />
              <div className="flex-1"><Skeleton className="mb-2 h-4 w-36" /><Skeleton className="h-3 w-56" /></div>
            </div>
          ))}
        </div>
      )}
      {!loading && entries.length === 0 && (
        <button
          onClick={onAdd}
          className="flex w-full flex-col items-center gap-3 px-8 py-14 text-center transition-colors hover:bg-surface2/60"
        >
          <span className="flex size-12 items-center justify-center rounded-2xl border-2 border-dashed border-line text-ink2">
            <Plus size={22} strokeWidth={2} />
          </span>
          <span>
            <span className="block text-[15px] font-semibold">Add your first server</span>
            <span className="mt-1 block max-w-sm text-[13px] text-ink2">
              Usually a LAN IP or Tailscale address, like <code className="font-mono text-[12px]">http://100.x.x.x:8096</code>
            </span>
          </span>
        </button>
      )}

      {visible.map(({ server, config, checking, connecting, error }, i) => {
        const version = config?.server_version;
        const drift = compareServerVersion(version);
        const online = !!config;
        const blocked = drift === "breaking";
        const last = relativeTime(server.lastConnected);
        const statusText = checking ? "Checking…" : online ? (last ? `Last opened ${last}` : "Ready to connect") : "Can't be reached right now";

        return (
          <div key={server.id} className={i > 0 || entries.length === 0 ? "border-t border-line" : ""}>
            <div className={`group relative flex min-w-0 items-center gap-3 px-4 py-4 transition-colors sm:gap-4 sm:px-5 ${blocked ? "" : "hover:bg-surface2/60"}`}>
              {/* Identity tile with status ring */}
              <span className="relative flex-none">
                <span
                  aria-hidden
                  className={`flex size-11 items-center justify-center rounded-xl bg-gradient-to-br font-display text-[15px] font-extrabold text-white ${tileGradient(server.name)} ${online ? "" : "opacity-40 saturate-50"}`}
                >
                  {monogram(server.name)}
                </span>
                <span
                  aria-hidden
                  className={`absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-surface ${checking ? "animate-pulse bg-line" : online ? "bg-ok" : "bg-crit/70"}`}
                />
              </span>

              {/* The row itself is the action */}
              <button
                onClick={() => onConnect(server)}
                disabled={connecting || blocked}
                aria-label={`Open ${server.name}`}
                className="min-w-0 flex-1 text-left outline-none"
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="break-words text-[15px] font-semibold">{server.name}</span>
                  {version && (version === "dev" || version === "unknown") && (
                    <span className="flex-none rounded border border-line bg-surface2 px-1.5 font-mono text-[10px] text-ink2">dev</span>
                  )}
                  {drift === "minor" && (
                    <span className="flex-none rounded border border-warn/40 bg-warn/10 px-1.5 font-mono text-[10px] text-warn">v{version}</span>
                  )}
                </span>
                <span className="mt-0.5 block text-[12.5px] leading-relaxed text-ink2">
                  <span className="break-all font-mono">{server.url}</span>
                  <span aria-hidden> · </span>
                  <span>{statusText}</span>
                </span>
              </button>

              <button
                aria-label={`Copy the address of ${server.name}`}
                title="Copy server address"
                onClick={() =>
                  void copyText(server.url).then((ok) =>
                    ok ? toast.success("Server address copied.") : toast.error("Couldn't copy the address."),
                  )
                }
                className="flex size-9 flex-none items-center justify-center rounded-lg text-ink2 transition-opacity hover:bg-surface2 hover:text-ink opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
              >
                <Copy size={15} strokeWidth={2} />
              </button>

              <button
                aria-label={`Remove ${server.name} from this device`}
                title="Remove from this device"
                onClick={() => onRemove(server)}
                className="flex size-9 flex-none items-center justify-center rounded-lg text-ink2 transition-opacity hover:bg-crit/10 hover:text-crit opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
              >
                <Trash2 size={15} strokeWidth={2} />
              </button>

              {connecting ? (
                <span className="flex size-8 flex-none items-center justify-center" aria-hidden>
                  <span className="size-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                </span>
              ) : blocked ? null : (
                <button
                  aria-label={`Connect to ${server.name}`}
                  title={`Connect to ${server.name}`}
                  onClick={() => onConnect(server)}
                  className="flex size-8 flex-none cursor-pointer items-center justify-center rounded-lg text-ink2 transition-all hover:bg-surface2 hover:text-accent group-hover:translate-x-0.5"
                >
                  <ChevronRight size={17} strokeWidth={2} />
                </button>
              )}
            </div>

            {blocked && (
              <p className="border-t border-crit/20 bg-crit/5 px-5 py-2.5 text-[12.5px] text-crit">
                This server runs v{version}, which this app can&apos;t talk to. Update the server, then come back.
              </p>
            )}
            {error && (
              <p role="alert" className="border-t border-crit/20 bg-crit/5 px-5 py-2.5 text-[12.5px] text-crit">{error}</p>
            )}
          </div>
        );
      })}

      {searchable && visible.length === 0 && (
        <p className="px-5 py-8 text-center text-[13px] text-ink2">No servers match “{query}”.</p>
      )}
      </div>
      {entries.length > 0 && (
        <button
          onClick={onAdd}
          className="flex w-full items-center gap-4 border-t border-line px-5 py-3.5 text-ink2 transition-colors hover:bg-surface2/60 hover:text-ink"
        >
          <span className="flex size-11 flex-none items-center justify-center rounded-xl border-2 border-dashed border-line">
            <Plus size={18} strokeWidth={2} />
          </span>
          <span className="text-[14px] font-medium">Add another server</span>
        </button>
      )}
    </div>
  );
}
