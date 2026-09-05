"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Check, ChevronDown, FileText, Globe, Layers, Link2, Minus, MessagesSquare, Paperclip, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName as vName, validateUrl as vUrl } from "@/lib/validation";
import { SectionHeader } from "@/components/ui/section-header";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import {
  attachContextFile,
  attachContextWeb,
  deleteContextPanelItems,
  fetchContextPanel,
  type ContextPanelItem,
} from "@/lib/api/context";
import { useConnectionStore } from "@/stores/connection.store";

export const CONTEXT_FILE_ACCEPT = ".pdf,.doc,.docx,.txt,.md,.csv,.json,.xml,.yaml,.yml,.py,.ts,.js";

const GROUP_ICONS: Record<string, typeof Layers> = {
  file: FileText,
  web: Globe,
  chat: MessagesSquare,
};

// Chat History leads (owner request); otherwise the server's registry order.
const TAB_ORDER = ["chat", "file", "web"];

// The Context tab: what the AI can see in this chat, split into sub-tabs (one
// per server panel group — "Files" and "Chat History"). Each tab supports
// multi-select with a bulk "Remove from context" — the server's
// delete-panel-items endpoint already takes a batch, so one call clears many.
export function ContextPanel({ projectId, topicId, onViewInChat }: { projectId: string; topicId: string; onViewInChat?: (messageId: string) => void }) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["context-panel", serverUrl, topicId] });

  const { data: groups, isLoading, error, refetch } = useQuery({
    queryKey: ["context-panel", serverUrl, topicId],
    queryFn: () => fetchContextPanel(projectId, topicId),
    enabled: !!serverUrl && !!token && !!projectId && !!topicId,
  });

  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [addingLink, setAddingLink] = useState(false);
  // Which sub-tab is open (by directive). null → default to the first group.
  const [activeDirective, setActiveDirective] = useState<string | null>(null);
  // Selected item ids WITHIN the active tab — cleared whenever the tab changes,
  // so a batch delete can never span two directives.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulk, setConfirmBulk] = useState(false);
  // Per-row single delete (kept alongside multi-select) — its own confirm.
  const [removingOne, setRemovingOne] = useState<ContextPanelItem | null>(null);

  const tabs = [...(groups ?? [])].sort(
    (a, b) => (TAB_ORDER.indexOf(a.directive) + 1 || 99) - (TAB_ORDER.indexOf(b.directive) + 1 || 99),
  );
  const active = tabs.find((g) => g.directive === activeDirective) ?? tabs[0];
  const activeKey = active?.directive;
  const fileGroup = tabs.find((g) => g.directive === "file"); // "Add file" target — exists regardless of the active tab
  const webGroup = tabs.find((g) => g.directive === "web"); // "Add link" target — web links are their own group

  const selectTab = (directive: string) => {
    setActiveDirective(directive);
    setSelected(new Set()); // selection is per-tab — clear synchronously on switch (no race)
  };

  const deletableIds = (active?.items ?? []).filter((i) => i.deletable).map((i) => i.id);
  const deletableSet = new Set(deletableIds);
  // Only ids belonging to the CURRENT tab count. selectTab clears on user
  // switches; this also guards the rare fallback where a refetch drops the active
  // group and relocates the tab, so a stale selection can never delete with the
  // wrong directive.
  const selectedInTab = [...selected].filter((id) => deletableSet.has(id));
  const allSelected = deletableIds.length > 0 && selectedInTab.length === deletableIds.length;
  const someSelected = selectedInTab.length > 0 && !allSelected;

  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(deletableIds));

  const attachFile = async (file: File) => {
    setUploading(true);
    const t = toast.loading(`Adding ${file.name} to context…`);
    try {
      const source = await attachContextFile(projectId, topicId, file);
      toast.dismiss(t);
      if (source.status === "error") toast.error(source.error || `${file.name} couldn't be processed — try a text-based file.`);
      else toast.success(`${file.name} added to context.`);
      invalidate();
    } catch (e) {
      toast.dismiss(t);
      toast.error(e instanceof Error ? e.message : `Couldn't add ${file.name}.`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeItems = useMutation({
    mutationFn: (ids: string[]) =>
      deleteContextPanelItems(projectId, topicId, ids.map((id) => ({ directive: activeKey!, id }))),
    onSuccess: (_data, ids) => {
      toast.success(ids.length === 1 ? "Removed from context." : `Removed ${ids.length} from context.`);
      setSelected(new Set());
      invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  const onWebTab = activeKey === "web";
  // File and web are both "sources" (vs chat messages) — for the Add-link form
  // placement and the source-vs-message wording in the remove confirmations.
  const isSourceTab = activeKey === "file" || activeKey === "web";

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4">
        <div>
          <input
            ref={fileRef}
            type="file"
            hidden
            accept={CONTEXT_FILE_ACCEPT}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void attachFile(f);
            }}
          />
          <SectionHeader
            title="Context"
            blurb="What the AI can see when it answers in this chat — personas use it automatically."
            actions={
              /* Always available while a Files group exists — using either one
                 jumps to the Files tab so the result is visible (fixes the
                 dead-end where the default Chat tab offered no way to add). */
              fileGroup || webGroup ? (
                <>
                  <Button size="sm" loading={uploading} onClick={() => { selectTab("file"); fileRef.current?.click(); }}>
                    <Paperclip size={14} strokeWidth={2} /> Add file
                  </Button>
                  <Button size="sm" onClick={() => { selectTab("web"); setAddingLink((v) => !v); }}>
                    <Link2 size={14} strokeWidth={2} /> Add link
                  </Button>
                </>
              ) : undefined
            }
          />

          {isLoading && (
            <div className="mt-5 flex flex-col gap-2.5" role="status" aria-label="Loading context">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
              <Skeleton className="h-9 w-2/3" />
            </div>
          )}
          {/* Full-panel error ONLY when there is no data to show. A refetch that
             fails AFTER a successful delete keeps the last-good panel + a slim
             retry rather than blanking everything (transient ≠ terminal). */}
          {error && !groups && (
            <p className="mt-5 text-[13px] text-crit">
              Couldn&apos;t load the context panel. <button className="underline" onClick={() => refetch()}>Retry</button>
            </p>
          )}
          {error && groups && (
            <p className="mt-3 text-[12px] text-warn" role="status">
              Couldn&apos;t refresh — showing the last loaded view. <button className="underline" onClick={() => refetch()}>Retry</button>
            </p>
          )}
          {!isLoading && !error && groups?.length === 0 && (
            <div className="mt-6">
              <EmptyState title="No context here yet" hint="Add a file or a link above to give the AI something to work with." />
            </div>
          )}

          {!isLoading && active && (
            <>
              {/* Sub-tabs — one per server panel group (Files / Chat History). */}
              <div
                role="tablist"
                aria-label="Context type"
                className="mt-4 flex overflow-hidden rounded-lg border border-line"
                onKeyDown={(e) => {
                  if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
                  e.preventDefault();
                  if (tabs.length <= 1) return; // one tab → nowhere to move (and don't disturb selection)
                  const i = tabs.findIndex((g) => g.directive === activeKey);
                  const ni = (i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
                  selectTab(tabs[ni].directive);
                  // APG tabs pattern: move focus to the newly selected tab.
                  e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[ni]?.focus();
                }}
              >
                {tabs.map((g, i) => {
                  const Icon = GROUP_ICONS[g.directive] ?? Layers;
                  const selectedTab = g.directive === activeKey;
                  return (
                    <button
                      key={g.directive}
                      role="tab"
                      id={`ctx-tab-${g.directive}`}
                      aria-controls="ctx-tabpanel"
                      aria-selected={selectedTab}
                      tabIndex={selectedTab ? 0 : -1}
                      onClick={() => selectTab(g.directive)}
                      className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-[13px] transition-colors ${
                        i > 0 ? "border-l border-line" : ""
                      } ${selectedTab ? "bg-accent/12 font-semibold text-accent" : "text-ink2 hover:bg-surface2/50 hover:text-ink"}`}
                    >
                      <Icon size={13} strokeWidth={2} /> {g.label}
                      <span className={`rounded-full px-1.5 text-[10.5px] tabular-nums ${selectedTab ? "bg-accent/20 text-accent" : "bg-surface2 text-ink2"}`}>{g.items.length}</span>
                    </button>
                  );
                })}
              </div>

              <div role="tabpanel" id="ctx-tabpanel" aria-labelledby={activeKey ? `ctx-tab-${activeKey}` : undefined}>
              {addingLink && onWebTab && (
                <AddLinkForm
                  onDone={() => {
                    setAddingLink(false);
                    invalidate();
                  }}
                  projectId={projectId}
                  topicId={topicId}
                />
              )}

              {active.items.length === 0 ? (
                <div className="mt-6">
                  {activeKey === "chat" ? (
                    <EmptyState title="No chat history in context" hint="Messages sent in this chat are available to the AI automatically." />
                  ) : (
                    <EmptyState title="Nothing in context yet" hint="Add a file or a link above — the AI will draw on it when answering here." />
                  )}
                </div>
              ) : (
                <>
                  {/* Select-all header — only when the tab has selectable items. */}
                  {deletableIds.length > 0 && (
                    <div className="mt-4 flex items-center gap-2.5 px-1">
                      <CheckBox checked={allSelected} indeterminate={someSelected} onToggle={toggleAll} label="Select all in this tab" />
                      <span className="text-[12px] text-ink2">
                        {selectedInTab.length > 0 ? `${selectedInTab.length} selected` : "Select all"}
                      </span>
                    </div>
                  )}
                  <ul className="mt-1.5 overflow-hidden rounded-xl border border-line bg-surface">
                    {active.items.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        directive={activeKey!}
                        selected={selected.has(item.id)}
                        onToggle={() => toggleOne(item.id)}
                        onRemoveOne={() => setRemovingOne(item)}
                        onViewInChat={onViewInChat}
                      />
                    ))}
                  </ul>
                </>
              )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Sticky bulk-action bar — appears once anything in THIS tab is selected. */}
      {selectedInTab.length > 0 && (
        <div className="flex-none border-t border-line bg-surface/95 px-4 py-2.5 backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[13px] text-ink2">
              <b className="text-ink tabular-nums">{selectedInTab.length}</b> selected
            </span>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => setSelected(new Set())}>Clear</Button>
              <Button size="sm" variant="danger" loading={removeItems.isPending} onClick={() => setConfirmBulk(true)}>
                <Trash2 size={14} strokeWidth={2} /> Remove from context
              </Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmBulk}
        onClose={() => setConfirmBulk(false)}
        onConfirm={() => {
          setConfirmBulk(false);
          removeItems.mutate(selectedInTab);
        }}
        title={selectedInTab.length === 1 ? "Remove from context?" : `Remove ${selectedInTab.length} items from context?`}
        body={
          <p>
            {isSourceTab
              ? "These sources will no longer be available to the AI when it answers here. You can add them again anytime."
              : "These messages will be excluded from what the AI sees here. They stay visible in the chat."}
          </p>
        }
        confirmLabel="Remove"
        loading={removeItems.isPending}
      />

      <ConfirmDialog
        open={!!removingOne}
        onClose={() => setRemovingOne(null)}
        onConfirm={() => {
          if (removingOne) removeItems.mutate([removingOne.id]);
          setRemovingOne(null);
        }}
        title="Remove from context?"
        body={
          <p>
            <b className="text-ink">{removingOne?.label}</b> will no longer be available to the AI when it answers here.
            {isSourceTab ? " You can add it again anytime." : " It stays visible in the chat."}
          </p>
        }
        confirmLabel="Remove"
        loading={removeItems.isPending}
      />
    </div>
  );
}

function ItemRow({ item, directive, selected, onToggle, onRemoveOne, onViewInChat }: {
  item: ContextPanelItem;
  directive: string;
  selected: boolean;
  onToggle: () => void;
  onRemoveOne: () => void;
  onViewInChat?: (messageId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = directive !== "chat";
  return (
    <li className="border-b border-line last:border-b-0">
      <div className="flex items-center gap-2.5 px-3.5 py-2">
        {item.deletable && <CheckBox checked={selected} onToggle={onToggle} label={`Select ${item.label}`} />}
        {hasDetails ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13.5px] hover:text-accent"
          >
            <span className="min-w-0 flex-1 truncate">{item.label}</span>
            <ChevronDown size={13} strokeWidth={2} className={`flex-none text-ink2 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
        ) : (
          <span className="min-w-0 flex-1 truncate text-[13.5px]">{item.label}</span>
        )}
        {typeof item.metadata.status === "string" && item.metadata.status !== "ready" && (
          <span className={`flex-none rounded-full px-2 py-0.5 text-[10.5px] font-medium ${item.metadata.status === "error" ? "bg-crit/10 text-crit" : "bg-warn/10 text-warn"}`}>
            {item.metadata.status === "error" ? "failed" : "processing"}
          </span>
        )}
        {directive === "chat" && onViewInChat && (
          <button
            aria-label="View in chat"
            title="View this message in the chat"
            onClick={() => onViewInChat(item.id)}
            className="flex size-7 flex-none items-center justify-center rounded-md text-ink2 hover:bg-accent/10 hover:text-accent"
          >
            <ArrowUpRight size={14} strokeWidth={2} />
          </button>
        )}
        {item.deletable && (
          <button
            aria-label={`Remove ${item.label} from context`}
            title="Remove from context"
            onClick={onRemoveOne}
            className="flex size-7 flex-none items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit"
          >
            <Trash2 size={14} strokeWidth={2} />
          </button>
        )}
      </div>
      {expanded && hasDetails && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line bg-surface2/50 px-3.5 py-2.5 text-[12px]">
          {typeof item.metadata.type === "string" && <><dt className="text-ink2">Type</dt><dd>{item.metadata.type}</dd></>}
          {typeof item.metadata.mime_type === "string" && <><dt className="text-ink2">Format</dt><dd className="truncate">{item.metadata.mime_type}</dd></>}
          {typeof item.metadata.size_kb === "number" && item.metadata.size_kb > 0 && <><dt className="text-ink2">Size</dt><dd>{item.metadata.size_kb} KB</dd></>}
          {typeof item.metadata.status === "string" && <><dt className="text-ink2">Status</dt><dd>{item.metadata.status}</dd></>}
          {typeof item.metadata.created_at === "string" && <><dt className="text-ink2">Added</dt><dd>{new Date(item.metadata.created_at).toLocaleString()}</dd></>}
        </dl>
      )}
    </li>
  );
}

// Themed tri-state checkbox (button + aria-checked) — native color styling is
// unreliable across the token themes, so we draw it.
function CheckBox({ checked, indeterminate, onToggle, label }: { checked: boolean; indeterminate?: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      aria-label={label}
      onClick={onToggle}
      className={`flex size-[18px] flex-none items-center justify-center rounded-[5px] border transition-colors ${
        checked || indeterminate ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface hover:border-ink2"
      }`}
    >
      {indeterminate ? <Minus size={12} strokeWidth={3} /> : checked ? <Check size={12} strokeWidth={3} /> : null}
    </button>
  );
}

function AddLinkForm({ projectId, topicId, onDone }: { projectId: string; topicId: string; onDone: () => void }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => attachContextWeb(projectId, topicId, url.trim(), name.trim() || undefined),
    onSuccess: (s) => {
      if (s.status === "error") toast.error(s.error || "That page couldn't be read.");
      else toast.success(`${s.name} added to context.`);
      onDone();
    },
    onError: (e) => toast.error(e.message),
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    const ue = vUrl(url, { label: "a web address" });
    if (ue) return setErr(ue);
    if (name.trim()) { const ne = vName(name, { label: "label", max: 80 }); if (ne) return setErr(ne); }
    add.mutate();
  };
  return (
    <form onSubmit={submit} noValidate className="mt-3 flex max-w-xl flex-col gap-3 rounded-xl border border-line bg-surface p-3.5">
      <div>
        <Label htmlFor="ctx-url" required>Web address</Label>
        <Input id="ctx-url" required placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus />
      </div>
      <div>
        <Label htmlFor="ctx-name">Name <span className="text-ink2">(optional)</span></Label>
        <Input id="ctx-name" placeholder="What to call it" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <FieldError>{err}</FieldError>
      <div className="flex gap-2">
        <Button type="button" size="sm" onClick={onDone}>Cancel</Button>
        <Button type="submit" size="sm" variant="primary" loading={add.isPending}>Add to context</Button>
      </div>
    </form>
  );
}
