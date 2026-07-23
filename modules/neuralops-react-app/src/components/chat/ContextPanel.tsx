/**
 * ContextPanel — M6 Context Management Controls
 *
 * Slide-in sidebar that shows all context sources for the active topic as a
 * generic tree.  Each top-level node is a context group (Files, Chat History,
 * …); children are individual items.  The UI adapts entirely to whatever the
 * backend returns — no hard-coded knowledge of specific source types.
 *
 * Features:
 *  - Search bar — filters items across all groups (label + full content)
 *  - Per-item checkboxes + group-level select-all
 *  - "Remove selected" action
 *  - Refreshes automatically when opened
 */

import { useEffect, useRef, useState, useMemo } from "react";
import {
  X,
  Trash2,
  RefreshCw,
  FileText,
  MessageSquare,
  Layers,
  CheckSquare,
  Square,
  MinusSquare,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { useContextPanel } from "@/hooks/useContextPanel";
import type { ContextPanelGroup, ContextPanelItem } from "@/services/context.service";

// ── Icon helper ──────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  "file-text": FileText,
  "message-square": MessageSquare,
  layers: Layers,
};

function GroupIcon({ name, className }: { name: string; className?: string }) {
  const Icon = ICON_MAP[name] ?? Layers;
  return <Icon className={className} />;
}

// ── Search filtering ─────────────────────────────────────────────────────────

function filterGroups(groups: ContextPanelGroup[], query: string): ContextPanelGroup[] {
  if (!query.trim()) return groups;
  const q = query.toLowerCase();
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.label.toLowerCase().includes(q)) return true;
        // Also search full content for chat messages
        const content = (item.metadata as Record<string, unknown>).content;
        if (typeof content === "string" && content.toLowerCase().includes(q)) return true;
        return false;
      }),
    }))
    .filter((group) => group.items.length > 0);
}

// ── Props ────────────────────────────────────────────────────────────────────

interface ContextPanelProps {
  open: boolean;
  onClose: () => void;
  projectId: string | null;
  topicId: string | null;
}

// ── Component ────────────────────────────────────────────────────────────────

export function ContextPanel({ open, onClose, projectId, topicId }: ContextPanelProps) {
  const {
    groups,
    loading,
    error,
    selected,
    deleting,
    load,
    toggleItem,
    toggleGroup,
    deleteSelected,
    isItemSelected,
    isGroupFullySelected,
  } = useContextPanel(projectId, topicId);

  const [query, setQuery] = useState("");

  // Filtered view — computed from raw groups + search query
  const visibleGroups = useMemo(() => filterGroups(groups, query), [groups, query]);

  // Load whenever the panel opens or the topic changes
  const prevTopicRef = useRef<string | null>(null);
  useEffect(() => {
    if (open && topicId !== prevTopicRef.current) {
      prevTopicRef.current = topicId;
      setQuery("");
      load();
    } else if (open && topicId === prevTopicRef.current && groups.length === 0 && !loading) {
      load();
    }
  }, [open, topicId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Clear search when panel closes
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const totalItems = groups.reduce((acc, g) => acc + g.items.length, 0);
  const hasSelection = selected.size > 0;
  const isFiltering = query.trim().length > 0;
  const filteredCount = visibleGroups.reduce((acc, g) => acc + g.items.length, 0);

  if (!open) return null;

  return (
    <div className="flex h-full w-80 flex-col border-l bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold">Context</span>
          {totalItems > 0 && (
            <Badge variant="secondary" className="text-xs">
              {isFiltering && filteredCount !== totalItems
                ? `${filteredCount} / ${totalItems}`
                : totalItems}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => { setQuery(""); load(); }}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} title="Close">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Search bar */}
      {totalItems > 0 && (
        <div className="border-b px-3 py-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search context…"
              className="h-7 pl-8 text-xs"
            />
            {query && (
              <button
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setQuery("")}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Action bar — visible when items are selected */}
      {hasSelection && (
        <div className="flex items-center justify-between border-b bg-muted/30 px-4 py-2">
          <span className="text-xs text-muted-foreground">
            {selected.size} selected
          </span>
          <Button
            variant="destructive"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={deleteSelected}
            disabled={deleting}
          >
            <Trash2 className="h-3 w-3" />
            {deleting ? "Removing…" : "Remove"}
          </Button>
        </div>
      )}

      {/* Body */}
      <ScrollArea className="flex-1">
        {loading && groups.length === 0 ? (
          <div className="flex h-32 items-center justify-center">
            <p className="text-xs text-muted-foreground">Loading context…</p>
          </div>
        ) : error ? (
          <div className="px-4 py-6 text-center">
            <p className="text-xs text-destructive">{error}</p>
            <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={load}>
              Retry
            </Button>
          </div>
        ) : totalItems === 0 ? (
          <div className="px-4 py-8 text-center">
            <Layers className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
            <p className="text-xs text-muted-foreground">No context attached yet.</p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              Use /file to add files to this conversation.
            </p>
          </div>
        ) : isFiltering && visibleGroups.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <Search className="mx-auto mb-2 h-7 w-7 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground">
              No results for <span className="font-medium">"{query}"</span>
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 text-xs"
              onClick={() => setQuery("")}
            >
              Clear search
            </Button>
          </div>
        ) : (
          <div className="divide-y">
            {visibleGroups.map((group) => (
              <ContextGroup
                key={group.directive}
                group={group}
                query={query}
                isItemSelected={isItemSelected}
                isGroupFullySelected={isGroupFullySelected}
                onToggleItem={toggleItem}
                onToggleGroup={toggleGroup}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

// ── Group ────────────────────────────────────────────────────────────────────

interface ContextGroupProps {
  group: ContextPanelGroup;
  query: string;
  isItemSelected: (directive: string, id: string) => boolean;
  isGroupFullySelected: (directive: string, ids: string[]) => boolean;
  onToggleItem: (directive: string, id: string) => void;
  onToggleGroup: (directive: string, ids: string[]) => void;
}

function ContextGroup({
  group,
  query,
  isItemSelected,
  isGroupFullySelected,
  onToggleItem,
  onToggleGroup,
}: ContextGroupProps) {
  const deletableItems = group.can_delete_items
    ? group.items.filter((i) => i.deletable)
    : [];
  const deletableIds = deletableItems.map((i) => i.id);
  const allSelected = isGroupFullySelected(group.directive, deletableIds);
  const someSelected =
    !allSelected && deletableIds.some((id) => isItemSelected(group.directive, id));

  if (group.items.length === 0) return null;

  return (
    <div className="py-2">
      {/* Group header */}
      <div className="flex items-center gap-2 px-4 py-1.5">
        {deletableItems.length > 0 && (
          <button
            className="flex-shrink-0 text-muted-foreground hover:text-foreground"
            onClick={() => onToggleGroup(group.directive, deletableIds)}
            aria-label={allSelected ? "Deselect all" : "Select all"}
          >
            {allSelected ? (
              <CheckSquare className="h-3.5 w-3.5" />
            ) : someSelected ? (
              <MinusSquare className="h-3.5 w-3.5" />
            ) : (
              <Square className="h-3.5 w-3.5" />
            )}
          </button>
        )}
        <GroupIcon name={group.icon} className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{group.label}</span>
        <Badge variant="outline" className="ml-auto text-xs px-1.5 py-0">
          {group.items.length}
        </Badge>
      </div>

      {/* Items */}
      <div>
        {group.items.map((item) => (
          <ContextItem
            key={item.id}
            item={item}
            directive={group.directive}
            canDelete={group.can_delete_items && item.deletable}
            selected={isItemSelected(group.directive, item.id)}
            query={query}
            onToggle={onToggleItem}
          />
        ))}
      </div>
    </div>
  );
}

// ── Item ─────────────────────────────────────────────────────────────────────

interface ContextItemProps {
  item: ContextPanelItem;
  directive: string;
  canDelete: boolean;
  selected: boolean;
  query: string;
  onToggle: (directive: string, id: string) => void;
}

/** Highlight the matching portion of text in bold */
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-200/60 dark:bg-yellow-500/30 rounded-[2px] px-0">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

function ContextItem({ item, directive, canDelete, selected, query, onToggle }: ContextItemProps) {
  const meta = item.metadata as Record<string, string | number | undefined>;
  const status = meta.status as string | undefined;
  const sizeKb = meta.size_kb as number | undefined;

  // For chat: show a match snippet from full content if the label doesn't contain the query
  const content = meta.content as string | undefined;
  const labelMatches = !query || item.label.toLowerCase().includes(query.toLowerCase());
  let snippet: string | undefined;
  if (query && !labelMatches && content) {
    const idx = content.toLowerCase().indexOf(query.toLowerCase());
    if (idx !== -1) {
      const start = Math.max(0, idx - 20);
      const end = Math.min(content.length, idx + query.length + 40);
      snippet =
        (start > 0 ? "…" : "") +
        content.slice(start, end) +
        (end < content.length ? "…" : "");
    }
  }

  return (
    <div
      className={`
        flex cursor-pointer items-start gap-2.5 px-4 py-2 text-sm
        hover:bg-muted/50 transition-colors
        ${selected ? "bg-muted/40" : ""}
      `}
      onClick={() => canDelete && onToggle(directive, item.id)}
    >
      {canDelete && (
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggle(directive, item.id)}
          className="mt-0.5 flex-shrink-0"
          onClick={(e) => e.stopPropagation()}
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs leading-snug text-foreground">
          <Highlight text={item.label} query={query} />
        </p>
        {snippet && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground/80 italic">
            <Highlight text={snippet} query={query} />
          </p>
        )}
        {(status || sizeKb !== undefined) && (
          <p className="mt-0.5 text-xs text-muted-foreground/70">
            {status && (
              <span
                className={
                  status === "ready"
                    ? "text-emerald-500"
                    : status === "error"
                      ? "text-destructive"
                      : "text-amber-500"
                }
              >
                {status}
              </span>
            )}
            {status && sizeKb !== undefined && " · "}
            {sizeKb !== undefined && `${sizeKb} KB`}
          </p>
        )}
      </div>
    </div>
  );
}
