"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Boxes, CornerDownLeft, Hash, MessageSquareText, Search, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useProjects, useTopics } from "@/hooks/use-workspace";
import { teardownRealtime } from "@/lib/realtime/centrifugo";
import { useTheme } from "@/theme/theme-provider";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelection } from "@/stores/selection.store";
import { useSearchShortcut } from "@/lib/platform";
import { buildEntries, filterEntries } from "./palette";

export function CommandPalette({ onAbout }: { onAbout: () => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const router = useRouter();
  const { sel, setChannel, setTopic } = useSelection();
  const projectsQ = useProjects();
  const { data: topics = [] } = useTopics(sel?.pid, sel?.cid);
  const projects = useMemo(() => projectsQ.data ?? [], [projectsQ.data]);
  const { theme, setTheme } = useTheme();
  const disconnect = useConnectionStore((s) => s.disconnect);
  const shortcut = useSearchShortcut();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        setQuery("");
        setActive(0);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const results = useMemo(() => filterEntries(buildEntries(projects, topics), query), [projects, topics, query]);

  // Keep the highlighted row visible when arrowing past the fold.
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const run = (i: number) => {
    const entry = results[i];
    if (!entry) return;
    if (!entry.select && !entry.action) return; // e.g. a channel-less project — nothing to open, keep the palette up
    setOpen(false);
    if (entry.select) {
      const { pid, cid, tid } = entry.select;
      if (tid) setTopic(pid, cid, tid);
      else setChannel(pid, cid);
      router.push("/w"); // the palette works from every page, not just the workspace
      return;
    }
    if (entry.action === "theme") setTheme(theme === "dark" ? "light" : "dark");
    if (entry.action === "server") {
      teardownRealtime(); // same teardown as the rail button — no stale socket on the launcher
      disconnect();
      router.push("/servers");
    }
    if (entry.action === "about") onAbout();
  };

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh]"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}
      // Consume Escape so the topic-view bubble listener doesn't ALSO close
      // in-chat search behind us (the designed capture/bubble Escape chain).
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); } }}
    >
      <div aria-hidden className="absolute inset-0 bg-black/45" onMouseDown={() => setOpen(false)} />
      <div role="dialog" aria-modal="true" aria-label="Command palette" className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
        <div className="flex items-center gap-3 px-4 py-3.5">
          <Search size={17} strokeWidth={2} className="flex-none text-ink2" />
          <input
            ref={inputRef}
            autoComplete="off"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); return; }
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              if (e.key === "Enter") { e.preventDefault(); run(active); }
            }}
            placeholder="Jump to projects, channels, this channel’s chats — or run an action…"
            className="w-full bg-transparent text-[15px] outline-none placeholder:text-ink2/60"
            aria-label="Search the workspace"
          />
          <kbd className="flex-none rounded-md border border-line bg-surface2 px-1.5 py-0.5 font-mono text-[10.5px] text-ink2">esc</kbd>
        </div>
        <ul ref={listRef} role="listbox" className="max-h-80 overflow-y-auto p-2">
          {projectsQ.isError && (
            <li className="flex items-center justify-between gap-2 px-3 py-2.5 text-[13px] text-crit">
              <span>Couldn’t load your workspace.</span>
              <button type="button" onClick={() => projectsQ.refetch()} className="flex-none cursor-pointer rounded-md border border-line px-2 py-0.5 text-[12px] text-ink2 hover:text-ink">Retry</button>
            </li>
          )}
          {projectsQ.isLoading && <li className="px-4 py-6 text-center text-[13.5px] text-ink2">Loading your workspace…</li>}
          {results.length === 0 && !projectsQ.isLoading && !projectsQ.isError && <li className="px-4 py-6 text-center text-[13.5px] text-ink2">Nothing matches “{query}”.</li>}
          {results.map((r, i) => {
            const Icon = r.kind === "project" ? Boxes : r.kind === "channel" ? Hash : r.kind === "topic" ? MessageSquareText : Zap;
            return (
              <li key={r.id} role="option" aria-selected={i === active}>
                <button
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[14px] ${i === active ? "bg-accent/10 text-ink" : "text-ink2 hover:bg-surface2"}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => run(i)}
                >
                  <span aria-hidden className={`flex size-7 flex-none items-center justify-center rounded-lg border ${i === active ? "border-accent/30 bg-accent/10 text-accent" : "border-line bg-surface2 text-ink2"}`}>
                    <Icon size={14} strokeWidth={2} />
                  </span>
                  <span title={r.label} className={`flex-1 truncate ${i === active ? "font-medium" : ""}`}>{r.label}</span>
                  {r.detail && <span className="truncate text-[12px] text-ink2">{r.detail}</span>}
                  {i === active && <CornerDownLeft size={13} strokeWidth={2} className="flex-none text-ink2" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
        <div className="flex items-center gap-4 border-t border-line px-4 py-2 text-[11px] text-ink2">
          <span><kbd className="rounded border border-line bg-surface2 px-1 font-mono">↑↓</kbd> navigate</span>
          <span><kbd className="rounded border border-line bg-surface2 px-1 font-mono">↵</kbd> open</span>
          <span className="ml-auto font-mono text-[10.5px]">{shortcut}</span>
        </div>
      </div>
    </div>
  );
}
