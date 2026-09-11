"use client";

import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, MessagesSquare } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import type { TransitionItem, UiMessage } from "@/lib/realtime/message-store";
import { sortKey } from "@/lib/realtime/message-store";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { useConnectionStore } from "@/stores/connection.store";
import { MessageItem, SystemSeparator } from "./message-item";
import type { KnownSets } from "@/lib/composer/mention-ranges";

// How close to the bottom counts as "following the stream".
const NEAR_BOTTOM_PX = 160;

// Layout effect on the client (scroll before paint — no flash), plain effect on
// the server (no SSR warning; it does nothing there anyway).
const useIsoLayoutEffect = typeof document !== "undefined" ? useLayoutEffect : useEffect;

function dayLabel(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 864e5);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], {
    weekday: "long",
    month: "long",
    day: "numeric",
    ...(d.getFullYear() !== today.getFullYear() ? { year: "numeric" as const } : {}),
  });
}

export function MessageList({ messages, transitions, loading, loadError, onRetry, onLoadOlder, jumpToId, onJumped, totalLoaded, known }: {
  messages: UiMessage[];
  transitions: TransitionItem[];
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
  onLoadOlder: () => Promise<number>;
  jumpToId?: string | null;
  onJumped?: () => void;
  totalLoaded?: number; // raw loaded count — pagination gate
  known?: KnownSets; // what counts as a real @name here — pills, like the composer
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [noMore, setNoMore] = useState(false);
  const showSkeleton = useDelayedLoading(loading);
  const selfId = useConnectionStore((s) => s.connection?.nucleusUserId);

  // atBottom is a ref (drives scroll logic without re-rendering); firstUnreadId
  // is state (drives the "new messages" pill). didInitial/lastNewestId track
  // per-mount progress — MessageList is keyed by topic id, so a topic switch
  // remounts and re-lands at the latest.
  const atBottomRef = useRef(true);
  const didInitial = useRef(false);
  const lastNewestId = useRef<string | null>(null);
  const [firstUnreadId, setFirstUnreadId] = useState<string | null>(null);

  const hasMessages = messages.length > 0;
  const newestId = messages.at(-1)?.id;
  // Content signature: changes on append AND on a streaming delta.
  const totalLength = messages.reduce((n, m) => n + m.content.length, 0) + messages.length;
  // The scroll container only renders once this is true (loading/skeleton/error
  // states render something else). The initial scroll keys on THIS becoming
  // true, not on message count: the delayed loader can hold the skeleton past
  // when messages arrive, so a count-based effect fired while the container was
  // absent and never re-fired — landing at the top.
  const messagesReady = !loading && !showSkeleton && !loadError && hasMessages;

  // Land at the latest the moment the message container mounts.
  useIsoLayoutEffect(() => {
    if (!messagesReady || didInitial.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    requestAnimationFrame(() => { const e = scrollRef.current; if (e) e.scrollTop = e.scrollHeight; }); // catch late layout (media/markdown)
    didInitial.current = true;
    lastNewestId.current = messages.at(-1)?.id ?? null;
    atBottomRef.current = true;
  }, [messagesReady]);

  // Attach the scroll listener once the scroll container exists (it's absent in
  // the loading/empty states). setState here lives in the event handler, not the
  // effect body, so it's fine under the set-state-in-effect rule.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
      atBottomRef.current = near;
      if (near) setFirstUnreadId(null); // scrolled back down — caught up
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [hasMessages]);

  // Follow the stream when at the bottom, or mark the first unread when scrolled
  // up. (Initial landing is the layout effect above.) DOM writes run inline; the
  // state update is deferred to rAF (set-state-in-effect rule).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !hasMessages || !didInitial.current) return;
    if (newestId && newestId !== lastNewestId.current) {
      const prevNewest = lastNewestId.current;
      lastNewestId.current = newestId;
      const newest = messages[messages.length - 1];
      const isOwn = !!newest?.senderId && newest.senderId === selfId; // your own send always follows to the bottom
      if (atBottomRef.current || isOwn) {
        el.scrollTop = el.scrollHeight;
        requestAnimationFrame(() => setFirstUnreadId(null));
      } else {
        // First unread = the message right after the last one seen at the bottom.
        const j = prevNewest ? messages.findIndex((m) => m.id === prevNewest) : -1;
        const firstUnread = (j >= 0 ? messages[j + 1]?.id : undefined) ?? newestId;
        requestAnimationFrame(() => setFirstUnreadId((prev) => prev ?? firstUnread));
      }
    } else if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight; // streaming delta / prepend while following — stay pinned
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run on content change; reads current refs/props by design
  }, [totalLength]);

  // Jump-to-message (search): center + flash. No cleanup-cancel (onJumped
  // immediately nulls the id, which would kill the removal timer) — and
  // remove+reflow so repeat jumps to the same message re-trigger the animation.
  useEffect(() => {
    if (!jumpToId) return;
    const target = scrollRef.current?.querySelector(`[data-msg-id="${CSS.escape(jumpToId)}"]`);
    if (target instanceof HTMLElement) {
      target.scrollIntoView({ block: "center" });
      target.classList.remove("nx-flash");
      void target.offsetWidth; // reflow restarts the animation
      target.classList.add("nx-flash");
      window.setTimeout(() => target.classList.remove("nx-flash"), 1_700);
    } else {
      // Never a silent no-op — the target lives outside the loaded window.
      toast.info("That message isn't loaded here — it may be in older history.");
    }
    onJumped?.();
  }, [jumpToId, onJumped]);

  const jumpToUnread = () => {
    const el = scrollRef.current;
    const target = firstUnreadId ? el?.querySelector(`[data-msg-id="${CSS.escape(firstUnreadId)}"]`) : null;
    if (target instanceof HTMLElement) target.scrollIntoView({ block: "start", behavior: "smooth" });
    else if (el) el.scrollTop = el.scrollHeight; // anchor scrolled off — fall back to the latest
    setFirstUnreadId(null);
  };

  // Flicker-free: fast loads show no skeleton at all; a skeleton that did
  // appear stays up long enough to read as intentional.
  if (loading || showSkeleton) {
    return showSkeleton ? (
      <div className="flex flex-1 flex-col gap-4 p-5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3"><Skeleton className="size-8 rounded-full" /><div className="flex-1"><Skeleton className="mb-2 h-3.5 w-40" /><Skeleton className="h-4 w-3/4" /></div></div>
        ))}
      </div>
    ) : (
      <div className="flex-1" aria-hidden />
    );
  }
  if (loadError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-[14px] text-crit">{loadError}</p>
        <Button size="sm" onClick={onRetry}>Retry</Button>
      </div>
    );
  }
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <EmptyState
          icon={<MessagesSquare strokeWidth={1.8} />}
          title="No messages yet"
          hint="Say something below — or @mention a persona to bring the AI in."
        />
      </div>
    );
  }

  // Interleave transitions after their anchor position.
  const items: Array<{ key: string; node: React.ReactNode; sort: number }> = messages.map((m) => ({
    key: m.id,
    node: <MessageItem message={m} known={known} />,
    sort: sortKey(m),
  }));
  for (const t of transitions) {
    items.push({
      key: t.key,
      sort: t.afterSortKey,
      node: <SystemSeparator content={t.toPersona && t.transitionType !== "return_control" ? `${t.fromPersona ?? "A persona"} → @${t.toPersona} (${t.transitionType === "delegation" ? "delegating" : "handing off"})` : t.content} />,
    });
  }
  items.sort((a, b) => a.sort - b.sort);

  const withDividers: Array<{ key: string; node: React.ReactNode; divider?: string }> = [];
  {
    let lastDay: string | null = null;
    for (const item of items) {
      const msg = messages.find((m) => m.id === item.key);
      const label = msg ? dayLabel(msg.createdAt) : null;
      withDividers.push({ key: item.key, node: item.node, divider: label && label !== lastDay ? label : undefined });
      if (label) lastDay = label;
    }
  }

  const unreadIdx = firstUnreadId ? messages.findIndex((m) => m.id === firstUnreadId) : -1;
  const unreadCount = unreadIdx >= 0 ? messages.length - unreadIdx : 0;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-3">
        {!noMore && (totalLoaded ?? messages.length) >= 100 && (
          <div className="flex justify-center pb-2">
            <Button size="sm" variant="ghost" loading={loadingOlder} onClick={async () => {
              setLoadingOlder(true);
              const el = scrollRef.current;
              const prevHeight = el?.scrollHeight ?? 0;
              const prevTop = el?.scrollTop ?? 0;
              try {
                const got = await onLoadOlder();
                if (got === 0) setNoMore(true); // genuinely at the beginning
                // Keep the reader anchored: Safari has no native scroll
                // anchoring, so compensate for the prepended height ourselves.
                requestAnimationFrame(() => {
                  if (el) el.scrollTop = el.scrollHeight - prevHeight + prevTop;
                });
              } catch {
                toast.error("Couldn't load earlier messages — try again.");
              } finally {
                setLoadingOlder(false);
              }
            }}>
              Load earlier messages
            </Button>
          </div>
        )}
        {withDividers.map((item) => (
          <Fragment key={item.key}>
            {item.divider && <DayDivider label={item.divider} />}
            {item.node}
          </Fragment>
        ))}
      </div>
      {unreadCount > 0 && (
        <button
          onClick={jumpToUnread}
          className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-accent-ink shadow-lg ring-1 ring-black/5 transition-transform hover:scale-105"
        >
          <ArrowDown size={14} strokeWidth={2.5} />
          {unreadCount} new message{unreadCount === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}

function DayDivider({ label }: { label: string }) {
  return (
    <div className="my-3 flex items-center gap-3 px-4" aria-label={label}>
      <span aria-hidden className="h-px flex-1 bg-line" />
      <span className="rounded-full border border-line bg-surface px-3 py-0.5 text-[11px] font-semibold text-ink2">{label}</span>
      <span aria-hidden className="h-px flex-1 bg-line" />
    </div>
  );
}
