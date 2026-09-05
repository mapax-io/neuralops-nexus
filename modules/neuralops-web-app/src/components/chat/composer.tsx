"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "tiptap-markdown";
import {
  AlignLeft,
  AtSign,
  BarChart3,
  Bold,
  Bot,
  Check,
  ClipboardList,
  Code2,
  GitBranch,
  Globe,
  History,
  Table,
  Terminal,
  CaseSensitive,
  Code,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Paperclip,
  Quote,
  SendHorizonal,
  Smile,
  Sparkles,
  SlashSquare,
  SquareCode,
  Strikethrough,
  User,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import dynamic from "next/dynamic";
import { MAX_MESSAGE_LENGTH, sendTyping } from "@/lib/api/chat";
import { absolutizeMedia } from "@/lib/api/client";
import { copyText } from "@/lib/browser";
import { listPersonas } from "@/lib/api/intelligence";
import { listTeam } from "@/lib/api/team";
import { changeUsername } from "@/lib/api/account";
import { attachContextFile } from "@/lib/api/context";
import { CONTEXT_FILE_ACCEPT } from "@/components/chat/context-panel";
import {
  activeDirective,
  isMentionableName,
  mentionTriggerAt,
  OUTPUT_DIRECTIVES,
  SESSION_DIRECTIVES,
  CONTEXT_DIRECTIVE,
  RESERVED_MENTIONS,
  toggleDirective,
} from "@/lib/composer/directives";
import { mentionCount, resolveSubmit, slashTriggerQuery, SLASH_COMMANDS } from "@/lib/composer/slash";
import { useUiStore } from "@/stores/ui.store";
import { useComposerMruStore, orderByRecency } from "@/stores/composer-mru.store";
import { MentionHighlight, mentionHighlightKey, type KnownSets } from "@/components/chat/mention-highlight";
import { fuzzyFilter, fuzzyScore } from "@/lib/composer/fuzzy";
import { inviteToProject } from "@/lib/api/team";
import { isCompanyAdmin } from "@/lib/permissions";
import { useConnectionStore } from "@/stores/connection.store";

// Lazy: the full emoji dataset (~hundreds of KB) loads on first open only.
const EmojiPicker = dynamic(() => import("@/components/chat/emoji-picker").then((m) => m.EmojiPicker), {
  ssr: false,
  loading: () => <div className="h-[360px] w-[352px] animate-pulse rounded-xl border border-line bg-surface" />,
});

const TYPING_THROTTLE_MS = 2_500;


// Slack-style rows: a real glyph per output directive, no "@" tiles.
const DIRECTIVE_ICONS: Record<string, typeof AtSign> = {
  chart: BarChart3,
  table: Table,
  diagram: GitBranch,
  form: ClipboardList,
  code: Code2,
  terminal: Terminal,
  html: Globe,
  text: AlignLeft,
};

import { drafts } from "@/lib/chat/drafts";

interface PopoverItem {
  id: string;
  label: string;
  detail?: string;
  avatar?: string | null;
  kind: "persona" | "human" | "directive" | "session" | "context";
  insert: string; // literal token to insert (ignored for "context")
  recent?: boolean; // floated to the top from the MRU list — shows a marker
}

// A live "@query" immediately before the caret, with ProseMirror positions
// so selecting an item can replace exactly that range.
interface ActiveTrigger {
  query: string;
  from: number;
  to: number;
}

function markdownOf(editor: Editor | null): string {
  if (!editor) return "";
  return (editor.storage as unknown as { markdown: { getMarkdown: () => string } }).markdown.getMarkdown();
}

export function Composer({ projectId, channelId, topicId, channelName, topicTitle, onSend, onShowSchedules, onSlashDialog, disabled }: {
  projectId: string;
  channelId: string;
  topicId: string;
  channelName?: string;
  topicTitle?: string;
  onSend: (content: string) => Promise<void>;
  onShowSchedules?: () => void;
  onSlashDialog?: (section: "models" | "mcp" | "personas") => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState(() => drafts.get(topicId) ?? "");
  const [sending, setSending] = useState(false);
  const [trigger, setTrigger] = useState<ActiveTrigger | null>(null);
  const [active, setActive] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const [dirMenuOpen, setDirMenuOpen] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [fmtOpen, setFmtOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const lastTypingRef = useRef(0);
  // Value-based suppression for the typing ping: holds the exact string a
  // PROGRAMMATIC change set (draft restore, directive toggle). A boolean flag
  // has ordering hazards (a same-string set never re-runs the effect and the
  // stale flag then eats the first real keystroke's ping).
  const progValueRef = useRef<string | null>(drafts.get(topicId) ?? "");
  const fileRef = useRef<HTMLInputElement>(null);
  // Whether the editor currently has focus — survives editor recreation
  // (destroying a focused element fires no blur), so the topic-switch effect
  // can tell "recreated while in use" from "opened a channel/topic".
  const editorFocusedRef = useRef(false);
  const placeholder = channelName
    ? topicTitle
      ? `Message #${channelName} › ${topicTitle}`
      : `Message #${channelName}`
    : "Message";

  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const email = useConnectionStore((s) => s.email);
  const qc = useQueryClient();
  const personasQ = useQuery({
    queryKey: ["personas", serverUrl, projectId],
    queryFn: () => listPersonas(projectId),
    enabled: !!serverUrl && !!token && !!projectId,
    staleTime: 60_000,
  });
  const personas = useMemo(() => personasQ.data ?? [], [personasQ.data]);
  // Teammates (humans) on this project — mentionable in @ with their own badge.
  const teamQ = useQuery({
    queryKey: ["team", serverUrl, projectId],
    queryFn: () => listTeam(projectId),
    enabled: !!serverUrl && !!token && !!projectId,
    staleTime: 60_000,
  });
  const humans = useMemo(
    () => (teamQ.data ?? []).filter((m) => m.member_type === "human" && isMentionableName(m.name)),
    [teamQ.data],
  );
  // The signed-in user's own mentionable name (matched by email) → the "you" pill.
  const selfName = useMemo(
    () => (email ? humans.find((m) => m.email.toLowerCase() === email.toLowerCase())?.name ?? null : null),
    [humans, email],
  );

  // "Recently used" ordering for the @ / popovers — device-scoped MRU, cleared
  // on sign-out (see composer-mru.store.ts).
  const recentPersonas = useComposerMruStore((s) => s.personas);
  const recentCommands = useComposerMruStore((s) => s.commands);
  const recordPersona = useComposerMruStore((s) => s.recordPersona);
  const recordCommand = useComposerMruStore((s) => s.recordCommand);

  const items = useMemo<PopoverItem[]>(() => {
    if (!trigger) return [];
    const q = trigger.query.toLowerCase();
    const recentSet = new Set(recentPersonas.map((n) => n.toLowerCase()));
    const matchedPersonas = fuzzyFilter(q, personas.filter((p) => isMentionableName(p.name)), (p) => p.name);
    // Recency only re-orders the UNFILTERED (bare "@") list. Once the user types a
    // query the fuzzy SCORE order wins — otherwise a recent-but-worse subsequence
    // match could float above (or, past the slice, hide) a better/exact match.
    const personaItems: PopoverItem[] = (q ? matchedPersonas : orderByRecency(matchedPersonas, (p) => p.name, recentPersonas))
      .slice(0, 6)
      .map((p) => ({
        id: `p:${p.id}`,
        label: p.name,
        // Optional chain on purpose: a server still on the pre-#99 contract must
        // not take the composer down — the label just degrades to "persona".
        detail: (p.mcp_servers?.length ?? 0) > 0 ? "persona · tools" : "persona",
        avatar: p.avatar,
        kind: "persona",
        insert: p.name,
        recent: recentSet.has(p.name.toLowerCase()),
      }));
    const humanItems: PopoverItem[] = fuzzyFilter(q, humans, (m) => m.name)
      .slice(0, 5)
      .map((m) => ({
        id: `h:${m.user_id}`,
        label: m.name,
        detail: m.name === selfName ? "you" : "teammate",
        avatar: m.avatar,
        kind: "human",
        insert: m.name,
      }));
    const sessionItems: PopoverItem[] = fuzzyFilter(q, SESSION_DIRECTIVES, (d) => d.name).map((d) => ({
      id: `s:${d.name}`,
      label: d.label,
      detail: d.hint,
      kind: "session",
      insert: d.insert,
    }));
    const contextItems: PopoverItem[] = fuzzyScore(q, CONTEXT_DIRECTIVE.name) !== null
      ? [{ id: "ctx:file", label: CONTEXT_DIRECTIVE.label, detail: CONTEXT_DIRECTIVE.hint, kind: "context", insert: "" }]
      : [];
    const directiveItems: PopoverItem[] = fuzzyFilter(q, OUTPUT_DIRECTIVES, (d) => d.name).map((d) => ({
      id: `d:${d.name}`,
      label: d.name,
      detail: d.hint,
      kind: "directive",
      insert: d.name,
    }));
    return [...personaItems, ...humanItems, ...sessionItems, ...contextItems, ...directiveItems].slice(0, 10);
  }, [trigger, personas, humans, selfName, recentPersonas]);

  const slashQuery = slashDismissed ? null : slashTriggerQuery(value);
  const myRole = useConnectionStore((st) => st.connection?.role);
  const setIntelCreate = useUiStore((u) => u.setIntelCreate);
  // Display gating by company role — Owner/Admin manage intelligence &
  // invites; everyone else gets the read/list commands. The server enforces
  // the real rules on every call.
  const companyAdmin = isCompanyAdmin(myRole);
  const availableCommands = SLASH_COMMANDS.filter((c) => {
    if (c.name === "invite" || c.name === "add-model" || c.name === "add-persona" ||
        c.name === "edit-persona" || c.name === "add-mcp") return companyAdmin;
    return true;
  });
  // Same rule as @: recency orders only the bare "/" list; a typed query ranks
  // by fuzzy score (so "/admdl" surfaces add-model by quality, not by recency).
  const slashMatches =
    slashQuery === null ? []
    : slashQuery === "" ? orderByRecency(availableCommands, (c) => c.name, recentCommands)
    : fuzzyFilter(slashQuery, availableCommands, (c) => c.name);
  const recentCommandSet = new Set(recentCommands.map((n) => n.toLowerCase()));
  const slashActive = Math.min(active, Math.max(0, slashMatches.length - 1));

  // handleKeyDown lives inside the editor config (created once) — read the
  // latest popover state through refs, never through closures.
  const kb = useRef<{
    items: PopoverItem[];
    active: number;
    slashMatches: typeof slashMatches;
    slashActive: number;
    trigger: ActiveTrigger | null;
    submit: () => Promise<void>;
  }>({ items: [], active: 0, slashMatches: [], slashActive: 0, trigger: null, submit: async () => {} });

  const editor = useEditor({
    immediatelyRender: false,
    // Toolbar pressed-states (isActive) must track caret moves and
    // stored-mark toggles, which don't change the doc.
    shouldRerenderOnTransaction: true,
    extensions: [
      StarterKit.configure({ heading: false, horizontalRule: false }),
      Link.configure({ openOnClick: false, autolink: true, HTMLAttributes: { rel: "noopener noreferrer" } }),
      Placeholder.configure({ placeholder }),
      Markdown.configure({ html: false, transformPastedText: true, transformCopiedText: true }),
      MentionHighlight,
    ],
    content: drafts.get(topicId) ?? "",
    editorProps: {
      attributes: { class: "nx-editor-content", "aria-label": "Message", role: "textbox" },
      // Clicking outside the composer dismisses the mention/slash popovers.
      handleDOMEvents: {
        focus: () => {
          editorFocusedRef.current = true;
          return false;
        },
        blur: () => {
          editorFocusedRef.current = false;
          setTrigger(null);
          setSlashDismissed(true);
          return false;
        },
      },
      handleKeyDown: (_view, e) => {
        const k = kb.current;
        if (k.slashMatches.length > 0) {
          const n = k.slashMatches.length;
          // Arrows WRAP (Up at the top → last, Down at the bottom → first).
          if (e.key === "ArrowDown") return (setActive((a) => (a + 1) % n), true);
          if (e.key === "ArrowUp") return (setActive((a) => (a - 1 + n) % n), true);
          if (e.key === "Tab" || e.key === "Enter") return (applySlashRef.current(k.slashMatches[k.slashActive].name), true);
          if (e.key === "Escape") return (setSlashDismissed(true), true);
        }
        if (k.trigger && k.items.length > 0) {
          const n = k.items.length;
          if (e.key === "ArrowDown") return (setActive((a) => (a + 1) % n), true);
          if (e.key === "ArrowUp") return (setActive((a) => (a - 1 + n) % n), true);
          if (e.key === "Tab" || e.key === "Enter") return (applyItemRef.current(k.items[Math.min(k.active, k.items.length - 1)]), true);
          if (e.key === "Escape") return (setTrigger(null), true);
        }
        if (e.key === "Enter" && e.shiftKey) {
          // Slack: inside a list, ANY Enter continues the list — Shift+Enter
          // must not fall back to a hard break inside the same bullet.
          const ed = editorRef.current;
          if (ed && (ed.isActive("bulletList") || ed.isActive("orderedList"))) {
            ed.chain().focus().splitListItem("listItem").run();
            return true;
          }
          return false; // soft break elsewhere (paragraphs, code blocks)
        }
        if (e.key === "Enter" && !e.shiftKey) {
          // Slack semantics: Enter sends — except inside code blocks and
          // lists, where it edits; ⌘/Ctrl+Enter always sends.
          const ed = editorRef.current;
          const editing = !!ed && (ed.isActive("codeBlock") || ed.isActive("bulletList") || ed.isActive("orderedList"));
          if (editing && !(e.metaKey || e.ctrlKey)) return false;
          // Let ``` (or ~~~) + Enter open a fenced code block: TipTap's input
          // rule fires on Enter, but our submit would otherwise swallow it, so
          // ```+Enter would just send a stray fence. Scoped to a bare marker.
          if (ed && !(e.metaKey || e.ctrlKey)) {
            const { $from, empty } = ed.state.selection;
            // Only when the caret is at the END of a paragraph that is ONLY the
            // fence marker — else ``` |trailing text would dead-end (no send, and
            // the input rule can't fire with trailing content).
            const atEnd = $from.parentOffset === $from.parent.content.size;
            if (empty && atEnd && $from.parent.type.name === "paragraph") {
              const before = $from.parent.textBetween(0, $from.parentOffset);
              // Match TipTap's OWN code-block input rule exactly (lowercase
              // letters only, no digits, case-sensitive) — a wider guard would
              // suppress send for a fence the rule then declines to convert,
              // stranding it (neither sent nor turned into a block).
              if (/^(```|~~~)([a-z]+)?$/.test(before)) return false;
            }
          }
          void k.submit();
          return true;
        }
        return false;
      },
    },
    onUpdate: ({ editor: ed }) => {
      const md = markdownOf(ed);
      setValue(md);
      drafts.set(topicId, md);
      setActive(0);
      setSlashDismissed(false);
      setDirMenuOpen(false);
      syncTrigger(ed);
    },
    onSelectionUpdate: ({ editor: ed }) => syncTrigger(ed),
    // Recreate when the placeholder changes (topic switch / auto-rename);
    // content is restored from the per-topic draft.
  }, [placeholder]);
  const editorRef = useRef<Editor | null>(null);

  // Push the pill-highlight known-set into the plugin: static @directives +
  // /commands, plus the (mentionable) personas as they load. The setMeta also
  // repaints, so pills appear on text already typed when the list arrives.
  useEffect(() => {
    if (!editor) return;
    const selfLower = selfName?.toLowerCase();
    const known: KnownSets = {
      mentions: new Set<string>([
        ...OUTPUT_DIRECTIVES.map((d) => d.name),
        "session",
        CONTEXT_DIRECTIVE.name,
        ...personas.filter((p) => isMentionableName(p.name)).map((p) => p.name.toLowerCase()),
      ]),
      self: new Set(selfLower ? [selfLower] : []),
      humans: new Set(humans.map((m) => m.name.toLowerCase()).filter((n) => n !== selfLower)),
      commands: new Set(SLASH_COMMANDS.map((c) => c.name)),
    };
    editor.view.dispatch(editor.state.tr.setMeta(mentionHighlightKey, known));
  }, [personas, humans, selfName, editor]);

  // Presence ping, throttled — driven by content changes (impure work lives
  // in an effect, not in the editor's render-created callbacks). Programmatic
  // value changes (draft restore, directive toggles) must NOT broadcast
  // "is typing" — only real keystrokes do.
  useEffect(() => {
    if (progValueRef.current !== null && value === progValueRef.current) {
      progValueRef.current = null;
      return;
    }
    if (!value.trim()) return;
    const now = Date.now();
    if (now - lastTypingRef.current > TYPING_THROTTLE_MS) {
      lastTypingRef.current = now;
      void sendTyping(projectId, channelId, topicId);
    }
  }, [value, projectId, channelId, topicId]);

  function syncTrigger(ed: Editor) {
    const { $from, empty } = ed.state.selection;
    if (!empty || !$from.parent.isTextblock || ed.isActive("codeBlock")) {
      setTrigger(null);
      return;
    }
    const textBefore = $from.parent.textBetween(0, $from.parentOffset, "\n", " ");
    const t = mentionTriggerAt(textBefore, textBefore.length);
    setTrigger(t ? { query: t.query, from: $from.pos - t.query.length - 1, to: $from.pos } : null);
  }

  // Topic switch: load that topic's draft, reset popovers. Opening a
  // channel/topic must NOT steal focus — refocus only restores focus across
  // an editor recreation (placeholder change after auto-rename) mid-typing.
  useEffect(() => {
    if (!editor) return;
    const raf = requestAnimationFrame(() => {
      const draft = drafts.get(topicId) ?? "";
      progValueRef.current = draft;
      editor.commands.setContent(draft);
      setValue(draft);
      setTrigger(null);
      setSlashDismissed(false);
      if (editorFocusedRef.current) editor.commands.focus("end");
    });
    return () => cancelAnimationFrame(raf);
  }, [topicId, editor]);

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [editor, disabled]);

  // Escape closes floating menus wherever focus is. preventDefault marks the
  // Escape as consumed so outer layers (in-chat search) don't
  // also react to the same keypress.
  useEffect(() => {
    if (!dirMenuOpen && !linkOpen) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setDirMenuOpen(false);
      setLinkOpen(false);
    };
    document.addEventListener("keydown", onEsc, true);
    return () => document.removeEventListener("keydown", onEsc, true);
  }, [dirMenuOpen, linkOpen]);

  // The directive menu is fully keyboard-driven: focus moves in on open,
  // arrows cycle the radio items (open-transition effect only).
  const dirMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!dirMenuOpen) return;
    const raf = requestAnimationFrame(() => dirMenuRef.current?.querySelector("button")?.focus());
    return () => cancelAnimationFrame(raf);
  }, [dirMenuOpen]);

  const applyItem = (item: PopoverItem) => {
    if (!editor || !trigger) return;
    if (item.kind === "context") {
      // @file strips the token and opens the picker — the upload goes to
      // context, not into the message text (matches the classic app).
      editor.chain().focus().deleteRange({ from: trigger.from, to: trigger.to }).run();
      setTrigger(null);
      fileRef.current?.click();
      return;
    }
    editor.chain().focus().deleteRange({ from: trigger.from, to: trigger.to }).insertContent(`@${item.insert} `).run();
    if (item.kind === "persona") recordPersona(item.insert); // MRU: float next time
    setTrigger(null);
  };
  const applyItemRef = useRef<(item: PopoverItem) => void>(() => {});

  const applySlash = (name: string) => {
    recordCommand(name); // MRU: float next time
    editor?.chain().focus().clearContent().insertContent(name === "swarm" ? "/swarm " : `/${name} `).run();
  };
  const applySlashRef = useRef<(name: string) => void>(() => {});

  // Count only names that ARE personas — a plain "@tomorrow" must not satisfy
  // the swarm gate. Fall back to the loose count ONLY while the list is still
  // loading (not on error, not when genuinely empty), so a failed fetch can't
  // silently let a bogus swarm through.
  const countPersonaMentions = (text: string) => {
    if (personasQ.isLoading) return mentionCount(text, RESERVED_MENTIONS);
    const known = new Set(personas.map((p) => p.name.toLowerCase()));
    const seen = new Set<string>();
    for (const m of text.matchAll(/@([\w]+)/g)) {
      const name = m[1].toLowerCase();
      if (!RESERVED_MENTIONS.has(name) && known.has(name)) seen.add(name);
    }
    return seen.size;
  };

  // Whole-text rewrites (directive/swarm toggles) go through markdown.
  const setMarkdown = (next: string) => {
    if (!editor) return;
    progValueRef.current = next;
    editor.commands.setContent(next);
    setValue(next);
    drafts.set(topicId, next);
    editor.commands.focus("end");
  };

  const submit = async () => {
    const content = markdownOf(editorRef.current).trim();
    if (!content || sending || content.length > MAX_MESSAGE_LENGTH) return;
    const action = resolveSubmit(content);
    if (action.kind === "invalid") {
      toast.info(action.message);
      return;
    }
    // The server silently degrades /swarm below two personas — block instead.
    if (/\/swarm\b/.test(content) && countPersonaMentions(content) < 2) {
      // On a persona-fetch error we can't verify mentions — say so truthfully
      // rather than telling the user to add personas that already exist.
      toast.info(personasQ.isError
        ? "Couldn’t check your personas just now — try again in a moment."
        : "Swarm needs at least two mentioned personas — add another @persona or remove /swarm.");
      return;
    }
    if (action.kind === "intel") {
      // In-place: the dialog opens over the chat (owner decision — slash
      // commands never navigate away). intelCreate makes the hosted tab
      // auto-open its create form.
      setIntelCreate(action.create);
      setMarkdown("");
      onSlashDialog?.(action.section);
      return;
    }
    if (action.kind === "schedules") {
      setMarkdown("");
      onShowSchedules?.();
      return;
    }
    if (action.kind === "invite") {
      setSending(true);
      try {
        const out = await inviteToProject(projectId, {
          ...(action.email ? { email: action.email } : { persona_name: action.personaName }),
          scope: action.scope,
          ...(action.scope === "topic" ? { topic_id: topicId } : {}),
          role: "member",
        });
        const msg = out.message || (action.personaName ? `@${action.personaName} added to this project.` : `Invitation sent to ${action.email}.`);
        if (out.invite_url) {
          // New users get a shareable link — surface it for 30s like the
          // old app did, so the inviter can paste it anywhere.
          toast.success(msg, {
            duration: 30_000,
            action: {
              label: "Copy invite link",
              onClick: () => void copyText(out.invite_url!).then((ok) => (ok ? toast.success("Invite link copied.") : toast.error("Couldn't copy the link."))),
            },
          });
        } else {
          toast.success(msg);
        }
        setMarkdown("");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Couldn't invite — try again.");
      } finally {
        setSending(false);
      }
      return;
    }
    if (action.kind === "changeusername") {
      setSending(true);
      try {
        const out = await changeUsername(action.newName, topicId);
        toast.success(`You're now "${out.display_name}" on this server.`);
        setMarkdown("");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not change your name.");
      } finally {
        setSending(false);
      }
      return;
    }
    setSending(true);
    try {
      await onSend(content);
      editorRef.current?.commands.clearContent(true);
      setValue("");
      drafts.delete(topicId);
      setTrigger(null);
    } catch {
      /* toast raised upstream; keep the draft */
    } finally {
      setSending(false);
    }
  };
  // Ref sync every render (editor callbacks read the latest through refs).
  useEffect(() => {
    kb.current = { items, active, slashMatches, slashActive, trigger, submit };
    applyItemRef.current = applyItem;
    applySlashRef.current = applySlash;
    editorRef.current = editor;
  });

  const attach = async (file: File) => {
    setUploading(true);
    const t = toast.loading(`Adding ${file.name} to the AI's context…`);
    try {
      const source = await attachContextFile(projectId, topicId, file);
      qc.invalidateQueries({ queryKey: ["context-panel", serverUrl, topicId] });
      toast.dismiss(t);
      if (source.status === "ready") {
        toast.success(`${file.name} added — personas in this topic can now use it.`);
      } else if (source.status === "error") {
        toast.error(source.error || `${file.name} couldn't be processed — try a text-based file.`);
      } else {
        toast.info(`${file.name} is still processing — it'll be available shortly.`);
      }
    } catch (e) {
      toast.dismiss(t);
      toast.error(e instanceof Error ? e.message : `Couldn't add ${file.name} to context.`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const applyLink = () => {
    const url = linkUrl.trim();
    if (!editor || !/^https?:\/\/\S+/.test(url)) {
      toast.info("Enter a full address, like https://example.com");
      return;
    }
    const { empty } = editor.state.selection;
    if (empty) {
      editor.chain().focus().insertContent([{ type: "text", text: url, marks: [{ type: "link", attrs: { href: url } }] }]).run();
    } else {
      editor.chain().focus().setLink({ href: url }).run();
    }
    setLinkOpen(false);
    setLinkUrl("");
  };

  const over = value.length > MAX_MESSAGE_LENGTH;
  const currentDirective = activeDirective(value);
  const swarmOn = /\/swarm\b/.test(value);
  const personaMentions = countPersonaMentions(value);

  return (
    <div className="relative flex-none px-3 pb-3 pt-1">
      {trigger && items.length > 0 && (
        <div role="listbox" aria-label="Mention suggestions" className="absolute bottom-full left-3 z-20 mb-1 w-[calc(100%-24px)] overflow-hidden rounded-xl border border-line bg-surface shadow-2xl sm:w-1/2 sm:min-w-96">
          {items.map((item, i) => (
            <button
              key={item.id}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()} /* a click must not blur the editor — blur unmounts this popover before onClick fires */
              onClick={() => applyItem(item)}
              className={`flex w-full items-center gap-2.5 px-3.5 py-2 text-left ${i === active ? "bg-accent/10" : ""}`}
            >
              {item.kind === "persona" || item.kind === "human" ? (
                item.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={absolutizeMedia(item.avatar) ?? undefined} alt="" className="size-6 flex-none rounded-full object-cover" />
                ) : item.kind === "human" ? (
                  <span className="flex size-6 flex-none items-center justify-center rounded-full bg-gradient-to-br from-stone-500 to-stone-700 text-white"><User size={13} strokeWidth={2} /></span>
                ) : (
                  <span className="flex size-6 flex-none items-center justify-center rounded-full bg-accent text-accent-ink"><Bot size={13} strokeWidth={2} /></span>
                )
              ) : (
                (() => {
                  const DirIcon = DIRECTIVE_ICONS[item.insert] ?? AtSign;
                  return (
                    <span className="flex size-6 flex-none items-center justify-center rounded-md border border-line bg-surface2 text-ink2">
                      <DirIcon size={13} strokeWidth={2} />
                    </span>
                  );
                })()
              )}
              <span className="flex-1 truncate text-[13.5px] font-medium">{item.label}</span>
              {item.recent && <History aria-label="Recently used" size={11} strokeWidth={2} className="flex-none text-ink2/70" />}
              {item.detail && <span className="truncate text-[11.5px] text-ink2">{item.detail}</span>}
            </button>
          ))}
        </div>
      )}

      {slashMatches.length > 0 && (
        <div role="listbox" aria-label="Commands" className="absolute bottom-full left-3 right-3 z-20 mb-1 overflow-hidden rounded-xl border border-line bg-surface shadow-2xl">
          {slashMatches.map((c, i) => (
            <button
              key={c.name}
              role="option"
              aria-selected={i === slashActive}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()} /* keep editor focus — see mention popover */
              onClick={() => applySlash(c.name)}
              className={`flex w-full items-baseline gap-2.5 px-3.5 py-2 text-left ${i === slashActive ? "bg-accent/10" : ""}`}
            >
              <span className="font-mono text-[13px] font-semibold text-accent">/{c.name}</span>
              <span className="flex-1 truncate text-[12px] text-ink2">{c.hint}</span>
              {recentCommandSet.has(c.name) && <History aria-label="Recently used" size={11} strokeWidth={2} className="flex-none text-ink2/70" />}
              <span className="hidden truncate font-mono text-[11px] text-ink2 sm:inline">{c.usage}</span>
            </button>
          ))}
        </div>
      )}

      {/* The directive menu escapes the input box's overflow clip — it anchors
          on the outer wrapper like the other popovers. */}
      {dirMenuOpen && (
        <>
          <button aria-label="Close menu" className="fixed inset-0 z-20 cursor-default" onClick={() => setDirMenuOpen(false)} />
          <div
            ref={dirMenuRef}
            role="menu"
            aria-label="Output format"
            onKeyDown={(e) => {
              if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
              e.preventDefault();
              const btns = Array.from(dirMenuRef.current?.querySelectorAll<HTMLButtonElement>("button[role=menuitemradio]") ?? []);
              const idx = btns.indexOf(document.activeElement as HTMLButtonElement);
              btns[e.key === "ArrowDown" ? (idx + 1) % btns.length : (idx - 1 + btns.length) % btns.length]?.focus();
            }}
            className="absolute bottom-full left-3 z-30 mb-1 w-72 max-w-[calc(100%-24px)] overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-2xl"
          >
            {OUTPUT_DIRECTIVES.filter((d) => d.name !== "text").map((d) => (
              <button
                key={d.name}
                role="menuitemradio"
                aria-checked={currentDirective === d.name}
                onClick={() => {
                  setMarkdown(toggleDirective(value, d.name));
                  setDirMenuOpen(false);
                }}
                className={`flex w-full items-baseline gap-2 px-3.5 py-1.5 text-left hover:bg-accent/10 ${currentDirective === d.name ? "text-accent" : ""}`}
              >
                <span className="w-20 flex-none font-mono text-[12px] font-semibold">@{d.name}</span>
                <span className="flex-1 truncate text-[12px] text-ink2">{d.hint}</span>
                {currentDirective === d.name && <Check aria-hidden size={13} strokeWidth={2.5} className="flex-none" />}
              </button>
            ))}
          </div>
        </>
      )}

      {emojiOpen && (
        <>
          <button aria-label="Close emoji picker" className="fixed inset-0 z-20 cursor-default" onClick={() => setEmojiOpen(false)} />
          <div className="absolute bottom-full left-3 z-30 mb-1 max-w-[calc(100%-24px)]">
            <EmojiPicker
              onClose={() => setEmojiOpen(false)}
              onPick={(emoji) => {
                setEmojiOpen(false);
                editor?.chain().focus().insertContent(emoji).run();
              }}
            />
          </div>
        </>
      )}

      {linkOpen && (
        <>
          <button aria-label="Close link editor" className="fixed inset-0 z-20 cursor-default" onClick={() => setLinkOpen(false)} />
          <div className="absolute bottom-full left-3 z-30 mb-1 flex w-80 max-w-[calc(100%-24px)] items-center gap-2 rounded-xl border border-line bg-surface p-2 shadow-2xl">
            <input
              autoFocus
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), applyLink())}
              placeholder="https://…"
              aria-label="Link address"
              className="w-full rounded-lg bg-surface2 px-3 py-2 font-mono text-[13px] outline-none ring-accent/60 focus:ring-2"
            />
            <button onClick={applyLink} className="flex h-8 flex-none items-center rounded-lg bg-accent px-3 text-[12.5px] font-semibold text-accent-ink hover:brightness-105">
              Link
            </button>
          </div>
        </>
      )}

      {/* Slack-anatomy input: formatting row (toggled), rich editor, toolbar. */}
      <div className={`rounded-xl border bg-surface transition-colors focus-within:border-accent ${over ? "border-crit" : "border-line"}`}>
        {fmtOpen && editor && (
          <div className="flex items-center gap-0.5 px-2 pb-0.5 pt-1.5" role="toolbar" aria-label="Text formatting">
            <ToolbarButton label="Bold (⌘B)" pressed={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}><Bold size={15} strokeWidth={2.2} /></ToolbarButton>
            <ToolbarButton label="Italic (⌘I)" pressed={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}><Italic size={15} strokeWidth={2} /></ToolbarButton>
            <ToolbarButton label="Strikethrough (⌘⇧S)" pressed={editor.isActive("strike")} onClick={() => editor.chain().focus().toggleStrike().run()}><Strikethrough size={15} strokeWidth={2} /></ToolbarButton>
            <span aria-hidden className="mx-1 h-4 w-px bg-line" />
            <ToolbarButton label="Link" pressed={editor.isActive("link") || linkOpen} onClick={() => setLinkOpen((o) => !o)}><LinkIcon size={15} strokeWidth={2} /></ToolbarButton>
            <span aria-hidden className="mx-1 h-4 w-px bg-line" />
            <ToolbarButton label="Numbered list" pressed={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}><ListOrdered size={15} strokeWidth={2} /></ToolbarButton>
            <ToolbarButton label="Bulleted list" pressed={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}><List size={15} strokeWidth={2} /></ToolbarButton>
            <ToolbarButton label="Quote (⌘⇧B)" pressed={editor.isActive("blockquote")} onClick={() => editor.chain().focus().toggleBlockquote().run()}><Quote size={15} strokeWidth={2} /></ToolbarButton>
            <span aria-hidden className="mx-1 h-4 w-px bg-line" />
            <ToolbarButton label="Inline code" pressed={editor.isActive("code")} onClick={() => editor.chain().focus().toggleCode().run()}><Code size={15} strokeWidth={2} /></ToolbarButton>
            <ToolbarButton label="Code block" pressed={editor.isActive("codeBlock")} onClick={() => editor.chain().focus().toggleCodeBlock().run()}><SquareCode size={15} strokeWidth={2} /></ToolbarButton>
          </div>
        )}
        <EditorContent editor={editor} className="nx-editor" />
        <div className="flex items-center gap-0.5 px-2 pb-1.5 pt-0.5">
          {/* Attach to AI context — the [+] every chat tool has, doing what THIS product means by files. */}
          <input
            ref={fileRef}
            type="file"
            hidden
            accept={CONTEXT_FILE_ACCEPT}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void attach(f);
            }}
          />
          <ToolbarButton label="Add a file to the AI's context" loading={uploading} onClick={() => fileRef.current?.click()}>
            <Paperclip size={16} strokeWidth={1.9} />
          </ToolbarButton>
          <span aria-hidden className="mx-1 h-4 w-px bg-line" />
          <ToolbarButton label="Formatting" pressed={fmtOpen} onClick={() => setFmtOpen((o) => !o)}>
            <CaseSensitive size={17} strokeWidth={1.9} />
          </ToolbarButton>
          <ToolbarButton label="Emoji" pressed={emojiOpen} onClick={() => setEmojiOpen((o) => !o)}>
            <Smile size={16} strokeWidth={1.9} />
          </ToolbarButton>
          <ToolbarButton
            label="Mention a persona"
            onClick={() => {
              if (!editor) return;
              // Space decision from the character BEFORE THE CARET — the end
              // of the document is the wrong place when the caret is mid-text.
              const { from } = editor.state.selection;
              const before = from > 1 ? editor.state.doc.textBetween(from - 1, from, "\n", " ") : "";
              const needsSpace = !!before && !/[\s@]/.test(before);
              editor.chain().focus().insertContent(needsSpace ? " @" : "@").run();
            }}
          >
            <AtSign size={16} strokeWidth={1.9} />
          </ToolbarButton>
          <ToolbarButton
            label={value.trim() ? "Commands need an empty message" : "Commands"}
            disabled={!!value.trim()} /* never destroy a typed draft */
            onClick={() => {
              editor?.chain().focus().clearContent().insertContent("/").run();
              setSlashDismissed(false);
            }}
          >
            <SlashSquare size={16} strokeWidth={1.9} />
          </ToolbarButton>
          <ToolbarButton label="Shape the answer (chart, table, diagram…)" pressed={!!currentDirective || dirMenuOpen} onClick={() => setDirMenuOpen((o) => !o)}>
            <Sparkles size={16} strokeWidth={1.9} />
          </ToolbarButton>
          <ToolbarButton
            label={personaMentions >= 2 || swarmOn ? "Swarm: personas collaborate on this task" : "Mention at least two personas to start a swarm"}
            pressed={swarmOn}
            disabled={!swarmOn && personaMentions < 2}
            onClick={() => {
              setMarkdown(/\s*\/swarm\b/.test(value) ? value.replace(/\s*\/swarm\b/, "").trim() : value.trim().length ? `${value.trim()} /swarm` : value);
            }}
          >
            <Workflow size={16} strokeWidth={1.9} className={swarmOn ? "text-live" : undefined} />
          </ToolbarButton>
          <span className="flex-1" />
          {value.length > MAX_MESSAGE_LENGTH - 400 && (
            <span className={`flex-none px-1 font-mono text-[11px] ${over ? "text-crit" : "text-ink2"}`}>
              {value.length}/{MAX_MESSAGE_LENGTH}
            </span>
          )}
          <button
            aria-label="Send message"
            onMouseDown={(e) => e.preventDefault()} /* keep editor focus — like the toolbar buttons */
            onClick={() => void submit()}
            disabled={disabled || sending || !value.trim() || over}
            className="flex h-7 w-9 flex-none items-center justify-center rounded-md bg-accent text-accent-ink transition-all hover:brightness-110 disabled:opacity-30 disabled:saturate-0"
          >
            <SendHorizonal size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
      {over && <p role="alert" className="mt-1.5 px-1 text-[12px] text-crit">Messages are limited to {MAX_MESSAGE_LENGTH} characters — attach long text as context instead.</p>}
    </div>
  );
}

function ToolbarButton({ label, onClick, children, disabled, pressed, loading }: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
  pressed?: boolean;
  loading?: boolean;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onMouseDown={(e) => e.preventDefault()} /* keep editor focus + selection */
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex size-8 flex-none items-center justify-center rounded-md transition-colors disabled:opacity-40 ${
        pressed ? "bg-accent/15 text-accent" : "text-ink2 hover:bg-surface2 hover:text-ink"
      }`}
    >
      {loading ? <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : children}
    </button>
  );
}
