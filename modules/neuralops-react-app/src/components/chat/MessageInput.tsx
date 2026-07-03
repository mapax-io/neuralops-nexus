import { useEffect, useRef, useState } from "react";
import { Paperclip, Send, X, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { inviteToProject } from "@/services/workspace.service";

const MOCK_PERSONAS = [
  { id: "p1", name: "Nova" },
  { id: "p2", name: "Sara" },
  { id: "p3", name: "Atlas" },
];

// Slash commands available in chat
const SLASH_COMMANDS = [
  {
    command: "/invite",
    description: "Invite someone to this topic or project",
    usage: "/invite email@example.com [project]",
    icon: UserPlus,
  },
];

export function MessageInput({
  disabled,
  onSend,
  placeholder,
  projectId,
  topicId,
}: {
  disabled?: boolean;
  onSend?: (text: string, file?: File) => void;
  placeholder?: string;
  projectId?: string;
  topicId?: string | null;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashQuery, setSlashQuery] = useState("");
  const [inviting, setInviting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const maxHeight = 6 * 24;
    ta.style.height = `${Math.min(ta.scrollHeight, maxHeight)}px`;
  }, [text]);

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setText(v);
    const caret = e.target.selectionStart;
    const upto = v.slice(0, caret);

    // @mention detection
    const mentionMatch = upto.match(/@(\w*)$/);
    if (mentionMatch) {
      setMentionOpen(true);
      setMentionQuery(mentionMatch[1].toLowerCase());
      setSlashOpen(false);
      return;
    }
    setMentionOpen(false);

    // slash command detection — only when at start of input
    const slashMatch = v.match(/^(\/\w*)$/);
    if (slashMatch) {
      setSlashOpen(true);
      setSlashQuery(slashMatch[1].toLowerCase());
    } else {
      setSlashOpen(false);
    }
  }

  function pickMention(name: string) {
    setText((t) => t.replace(/@(\w*)$/, `@${name} `));
    setMentionOpen(false);
    textareaRef.current?.focus();
  }

  function pickSlashCommand(command: string) {
    setText(command + " ");
    setSlashOpen(false);
    textareaRef.current?.focus();
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Escape") {
      setSlashOpen(false);
      setMentionOpen(false);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  async function handleInviteCommand(trimmed: string) {
    if (!projectId) {
      toast.error("No active project — cannot send invite.");
      return;
    }
    // Parse: /invite email [project]
    // e.g. "/invite noamanfaisal@gmail.com" or "/invite noamanfaisal@gmail.com project"
    const parts = trimmed.split(/\s+/);
    // parts[0] = "/invite", parts[1] = email, parts[2] = optional "project"
    const email = parts[1];
    const scopeKeyword = parts[2]?.toLowerCase();

    if (!email) {
      toast.error('Usage: /invite email@example.com [project]');
      return;
    }

    const scope = scopeKeyword === "project" ? "project" : "topic";

    setInviting(true);
    try {
      const result = await inviteToProject(projectId, {
        email,
        scope,
        topic_id: scope === "topic" ? (topicId ?? undefined) : undefined,
        role: "member",
      });

      if (result.is_new_user && result.server_url) {
        // New user: tell the inviter what server address to share
        toast.success(result.message, {
          description: `Server address: ${result.server_url}`,
          action: {
            label: "Copy address",
            onClick: () => {
              navigator.clipboard.writeText(result.server_url!);
              toast.success("Server address copied");
            },
          },
          duration: 20_000,
        });
      } else {
        // Existing user added directly, or no server URL configured
        toast.success(result.message);
      }
      setText("");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Invite failed";
      toast.error(msg);
    } finally {
      setInviting(false);
    }
  }

  function submit() {
    const trimmed = text.trim();
    if (!trimmed && !file) return;

    // Intercept slash commands
    if (trimmed.startsWith("/invite")) {
      handleInviteCommand(trimmed);
      return;
    }

    // Other slash commands (future)
    if (trimmed.startsWith("/") && !trimmed.includes(" ")) {
      toast.info(`Unknown command: ${trimmed}`);
      return;
    }

    onSend?.(trimmed, file ?? undefined);
    setText("");
    setFile(null);
  }

  if (disabled) {
    return (
      <div className="border-t border-sidebar-border bg-sidebar px-4 py-3 text-center text-sm text-foreground-muted">
        {placeholder ?? "Select a conversation to start messaging"}
      </div>
    );
  }

  const mentionSuggestions = MOCK_PERSONAS.filter((p) =>
    p.name.toLowerCase().startsWith(mentionQuery),
  );

  const slashSuggestions = SLASH_COMMANDS.filter((c) =>
    c.command.startsWith(slashQuery),
  );

  // Detect if user is mid-invite so we can show a usage hint
  const isTypingInvite = text.startsWith("/invite ");
  const inviteParts = text.trim().split(/\s+/);
  const inviteHasEmail = inviteParts.length >= 2 && inviteParts[1].includes("@");

  return (
    <div className="relative border-t border-sidebar-border bg-sidebar px-3 py-3">
      {file && (
        <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-border bg-card px-2 py-1 text-xs">
          <span className="max-w-[240px] truncate">{file.name}</span>
          <button
            type="button"
            onClick={() => setFile(null)}
            className="text-foreground-muted hover:text-foreground"
            aria-label="Remove file"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Slash command picker */}
      {slashOpen && slashSuggestions.length > 0 && (
        <div className="absolute bottom-full left-3 mb-2 w-72 rounded-md border border-border bg-popover p-1 shadow-md">
          {slashSuggestions.map((cmd) => (
            <button
              key={cmd.command}
              type="button"
              onClick={() => pickSlashCommand(cmd.command)}
              className="flex w-full items-start gap-2 rounded px-2 py-2 text-left hover:bg-accent hover:text-accent-foreground"
            >
              <cmd.icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <div>
                <div className="text-sm font-medium">{cmd.command}</div>
                <div className="text-xs text-muted-foreground">{cmd.usage}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* /invite usage hint */}
      {isTypingInvite && !inviteHasEmail && (
        <div className="absolute bottom-full left-3 mb-2 w-72 rounded-md border border-border bg-popover px-3 py-2 shadow-md">
          <div className="flex items-center gap-2">
            <UserPlus className="h-4 w-4 shrink-0 text-primary" />
            <div>
              <div className="text-xs font-medium text-foreground">Invite someone</div>
              <div className="text-xs text-muted-foreground">
                <code>/invite email@example.com</code> — add to this topic
              </div>
              <div className="text-xs text-muted-foreground">
                <code>/invite email@example.com project</code> — add to project
              </div>
            </div>
          </div>
        </div>
      )}

      {/* @mention picker */}
      {mentionOpen && mentionSuggestions.length > 0 && (
        <div className="absolute bottom-full left-3 mb-2 w-56 rounded-md border border-border bg-popover p-1 shadow-md">
          {mentionSuggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => pickMention(s.name)}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[10px] font-semibold text-accent-foreground">
                {s.name.slice(0, 1)}
              </span>
              {s.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept="image/*,.pdf,.doc,.docx,.txt,.csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8 shrink-0"
          onClick={() => fileInputRef.current?.click()}
          aria-label="Attach file"
        >
          <Paperclip className="h-4 w-4" />
        </Button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKey}
          rows={1}
          placeholder="Message... (/ for commands, @ to mention)"
          className="max-h-36 min-h-[24px] flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-foreground-muted"
        />
        <Button
          type="button"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={submit}
          disabled={(!text.trim() && !file) || inviting}
          aria-label="Send"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
