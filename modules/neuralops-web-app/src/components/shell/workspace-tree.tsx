"use client";

import { useState } from "react";
import { Users,
  Boxes,
  Brain,
  ChevronRight,
  FlaskConical,
  FolderPlus,
  Globe,
  Hash,
  LineChart,
  Plus,
  Rocket,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { absolutizeMedia } from "@/lib/api/client";
import { tileGradient } from "@/components/servers/server-chooser";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TeamDialog } from "@/components/shell/team-dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { validateName } from "@/lib/validation";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import {
  useArchiveChannel,
  useArchiveProject,
  useCreateChannel,
  useCreateProject,
  useMembers,
  useProjects,
  useTopics,
} from "@/hooks/use-workspace";
import { useConnectionStore } from "@/stores/connection.store";
import { isCompanyAdmin } from "@/lib/permissions";
import { useSelection } from "@/stores/selection.store";
import type { Channel, Project } from "@/lib/api/workspace";

// Each project gets a stable icon + tint from its id — visual identity at a
// glance, same hashing idea as the server tiles.
const PROJECT_MARKS: Array<[typeof Rocket, string]> = [
  [Rocket, "text-sky-500"],
  [Globe, "text-cyan-500"],
  [Brain, "text-rose-500"],
  [Boxes, "text-emerald-500"],
  [FlaskConical, "text-amber-500"],
  [LineChart, "text-blue-500"],
];

function projectMark(id: string) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PROJECT_MARKS[h % PROJECT_MARKS.length];
}

export function WorkspaceTree() {
  const { data: projects, isLoading, error, refetch } = useProjects();
  // Selection lives in a store, not the URL — ids never reach the address bar.
  const { sel } = useSelection();
  const role = useConnectionStore((s) => s.connection?.role);
  // project.create is COMPANY scope -- Company Admin/Owner only.
  const canManage = isCompanyAdmin(role);
  const [creating, setCreating] = useState(false);
  const companyName = useConnectionStore((s) => s.connection?.companyName);

  return (
    <aside aria-label="Projects and channels" className="flex w-64 flex-none flex-col border-r border-line bg-rail">
      {/* Below lg the tree is a drawer and the top bar hides the workspace
          name — this header titles the drawer. From lg up the name lives in
          the top bar (after the app mark), so no duplicate here. Wraps, never
          truncates. */}
      <div className="flex items-center gap-2 border-b border-line px-4 py-3 lg:hidden">
        <p className="font-display text-[14px] font-bold break-words">{companyName ?? "Workspace"}</p>
      </div>
      <div className="flex-1 overflow-y-auto p-2.5">
        <div className="mb-1.5 flex items-center px-1.5">
          <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[.12em] text-ink2">Projects</p>
          <span className="flex-1" />
          {canManage && (
            <button aria-label="New project" title="New project" onClick={() => setCreating(true)} className="flex size-6 items-center justify-center rounded-md text-ink2 hover:bg-surface hover:text-ink"><Plus size={15} strokeWidth={2} /></button>
          )}
        </div>
        {isLoading && <div className="flex flex-col gap-2 px-1.5 pt-1"><Skeleton className="h-7" /><Skeleton className="h-7" /><Skeleton className="h-7 w-2/3" /></div>}
        {error && (
          <div className="px-1.5 pt-2 text-[13px] text-crit">
            Couldn&apos;t load projects. <button className="underline" onClick={() => refetch()}>Retry</button>
          </div>
        )}
        {projects?.length === 0 && (
          <EmptyState
            title="No projects yet"
            hint={canManage ? "Create your first project to start working." : "Ask an admin to add you to a project."}
            action={canManage ? <Button size="sm" onClick={() => setCreating(true)}>New project</Button> : undefined}
          />
        )}
        {projects?.map((p) => <ProjectNode key={p.id} project={p} activeChannelId={sel?.cid} role={role} />)}
        <DirectMessagesSection />
      </div>
      <CreateProjectDialog open={creating} onClose={() => setCreating(false)} />
    </aside>
  );
}

// Slack-style DM section. The server has no DM routes yet (see
// docs/OPEN-ITEMS.md) — real teammates are listed, actions announce the
// feature is under development.
function DirectMessagesSection() {
  const { data: members, isLoading } = useMembers();
  const email = useConnectionStore((s) => s.email);
  const soon = () => toast.info("Direct messages are under development — coming soon.");

  return (
    <div className="mt-5">
      <div className="mb-1.5 flex items-center px-1.5">
        <p className="font-mono text-[10.5px] font-semibold uppercase tracking-[.12em] text-ink2">Direct messages</p>
        <span className="ml-1.5 rounded-full border border-accent/30 bg-accent/10 px-1.5 text-[9.5px] font-semibold text-accent">soon</span>
        <span className="flex-1" />
        <button aria-label="New direct message" title="Direct messages are coming soon" onClick={soon} className="flex size-6 items-center justify-center rounded-md text-ink2 hover:bg-surface hover:text-ink">
          <Plus size={15} strokeWidth={2} />
        </button>
      </div>
      {isLoading && <div className="flex flex-col gap-1.5 px-1.5"><Skeleton className="h-6" /><Skeleton className="h-6 w-3/4" /></div>}
      <ul>
        {members?.map((m) => {
          const isSelf = !!email && m.email.toLowerCase() === email.toLowerCase();
          const name = m.email.split("@")[0];
          const avatar = absolutizeMedia(m.avatar);
          return (
            <li key={m.user_id}>
              <button
                onClick={soon}
                title="Direct messages are coming soon"
                className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] text-ink2 hover:bg-surface hover:text-ink"
              >
                <span className="flex size-5 flex-none items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-stone-500 to-stone-700 text-[9px] font-bold text-white">
                  {avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
                    <img src={avatar} alt="" className="size-full object-cover" />
                  ) : (
                    name[0]?.toUpperCase()
                  )}
                </span>
                <span className="min-w-0 flex-1 truncate">
                  {name}
                  {isSelf && <span className="text-ink2/70"> (you)</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ProjectNode({ project, activeChannelId, role }: { project: Project; activeChannelId?: string; role?: string | null }) {
  // channel.create / project.archive / channel.archive are PROJECT-scope
  // Admin rights -- a Project Admin reaches them without a company role.
  const canManage = isCompanyAdmin(role);
  const { sel, clearSelection } = useSelection();
  const [open, setOpen] = useState(true);
  const [addingChannel, setAddingChannel] = useState(false);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const [managingTeam, setManagingTeam] = useState(false);
  const archive = useArchiveProject(() => {
    if (sel?.pid === project.id) clearSelection();
  });
  const [Mark, tint] = projectMark(project.id);

  return (
    <div className="mb-2">
      <div className="group flex items-center rounded-lg px-1.5 py-1 hover:bg-surface">
        <button aria-expanded={open} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-[13.5px] font-semibold">
          <ChevronRight aria-hidden size={12} strokeWidth={2.25} className={`flex-none text-ink2 transition-transform ${open ? "rotate-90" : ""}`} />
          <Mark aria-hidden size={14} strokeWidth={2} className={`flex-none ${tint}`} />
          {/* Full name, wrapped — never an ellipsis (matches the topics panel). */}
          <span title={project.name} className="min-w-0 break-words leading-tight">{project.name}</span>
        </button>
        {canManage && (
          <>
            <button aria-label={`Manage team for ${project.name}`} title="Manage team" onClick={() => setManagingTeam(true)} className="flex size-6 items-center justify-center rounded text-ink2 hover:text-ink opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"><Users size={13} strokeWidth={2} /></button>
            <button aria-label={`Archive project ${project.name}`} title="Archive project" onClick={() => setConfirmingArchive(true)} className="flex size-6 items-center justify-center rounded text-ink2 hover:text-crit opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"><Trash2 size={13} strokeWidth={2} /></button>
            <button aria-label={`New channel in ${project.name}`} title="New channel" onClick={() => setAddingChannel(true)} className="flex size-6 items-center justify-center rounded text-ink2 hover:text-ink opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"><Plus size={14} strokeWidth={2} /></button>
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirmingArchive}
        onClose={() => setConfirmingArchive(false)}
        onConfirm={() => {
          setConfirmingArchive(false);
          archive.mutate(project.id);
        }}
        title="Archive this project?"
        body={
          <p>
            <b className="text-ink">{project.name}</b> and every channel and chat inside it will be hidden for
            the whole team. A server admin can restore it later.
          </p>
        }
        confirmLabel="Archive project"
        loading={archive.isPending}
      />
      <TeamDialog pid={project.id} projectName={project.name} open={managingTeam} onClose={() => setManagingTeam(false)} />
      {open && (
        <ul className="ml-3 border-l border-line pl-1.5">
          {project.channels.map((c) => (
            <ChannelNode key={c.id} projectId={project.id} channel={c} isActive={c.id === activeChannelId} canManage={canManage} />
          ))}
          {project.channels.length === 0 && <li className="px-2 py-1 text-[12.5px] text-ink2">No channels yet</li>}
        </ul>
      )}
      <CreateChannelDialog projectId={project.id} projectName={project.name} existingNames={project.channels.map((c) => c.name)} open={addingChannel} onClose={() => setAddingChannel(false)} />
    </div>
  );
}

// The tree stops at channels — a channel's chats live in the right-side
// panel (ChatListPanel), thread-panel style. Clicking a channel opens it.
function ChannelNode({ projectId, channel, isActive, canManage }: { projectId: string; channel: Channel; isActive: boolean; canManage: boolean }) {
  const { sel, setChannel, clearSelection } = useSelection();
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const archiveChannel = useArchiveChannel(projectId, () => {
    if (sel?.cid === channel.id) clearSelection();
  });
  // Fetched here (not only in the panel) so the unread dot shows for every
  // channel, selected or not.
  const { data: topics } = useTopics(projectId, channel.id);
  const unreadCount = topics?.filter((t) => t.has_unread && t.id !== sel?.tid).length ?? 0;

  return (
    <li>
      <div className={`group flex items-center rounded-md pl-1 pr-0.5 ${isActive ? "bg-accent/10" : "hover:bg-surface"}`}>
        <button
          onClick={() => setChannel(projectId, channel.id)}
          aria-current={isActive ? "page" : undefined}
          className={`flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left text-[13.5px] ${isActive ? "font-semibold text-ink" : "text-ink2 hover:text-ink"}`}
        >
          {/* Rocket.Chat-style letter tile: stable per-channel identity at a glance */}
          <span aria-hidden className={`flex size-5 flex-none items-center justify-center rounded-md bg-gradient-to-br text-[10px] font-bold text-white ${tileGradient(channel.name)}`}>
            {channel.name.replace(/[^\p{L}\p{N}]/gu, "")[0]?.toUpperCase() ?? "#"}
          </span>
          <Hash aria-hidden size={13} strokeWidth={2} className="flex-none text-ink2" />
          {/* Full name, wrapped — never an ellipsis. */}
          <span title={channel.name} className={`min-w-0 break-words leading-tight ${unreadCount > 0 ? "font-semibold text-ink" : ""}`}>{channel.name}</span>
        </button>
        {unreadCount > 0 && (
          <span role="status" aria-label={`${unreadCount} topics with new messages`} title={`${unreadCount} ${unreadCount === 1 ? "topic" : "topics"} with new messages`}
            className="ml-1 size-2 flex-none rounded-full bg-accent"
          />
        )}
        {canManage && (
          <button
            aria-label={`Archive channel ${channel.name}`}
            title="Archive channel"
            onClick={() => setConfirmingArchive(true)}
            className="flex size-6 flex-none items-center justify-center rounded text-ink2 hover:text-crit opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Trash2 size={12.5} strokeWidth={2} />
          </button>
        )}
      </div>
      <ConfirmDialog
        open={confirmingArchive}
        onClose={() => setConfirmingArchive(false)}
        onConfirm={() => {
          setConfirmingArchive(false);
          archiveChannel.mutate(channel.id);
        }}
        title="Archive this channel?"
        body={
          <p>
            <b className="text-ink">#{channel.name}</b> and its chats will be hidden for the whole team. A
            server admin can restore it later.
          </p>
        }
        confirmLabel="Archive channel"
        loading={archiveChannel.isPending}
      />
    </li>
  );
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { setChannel } = useSelection();
  const { data: projects } = useProjects();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Projects are stored under a kebab-cased name, so the duplicate check must
  // compare the SAME normalized form — not the raw typed string (else
  // "Customer Research" slips past an existing "customer-research").
  const toSlug = (v: string) => v.trim().toLowerCase().replace(/\s+/g, "-");
  const validate = (v: string): string | null => {
    const base = validateName(v, { label: "project name", max: 60 });
    if (base) return base;
    const s = toSlug(v);
    if (projects?.some((p) => p.name.toLowerCase() === s)) return `A project named "${v.trim()}" already exists.`;
    return null;
  };
  const reset = () => {
    setName("");
    setDescription("");
    setNameErr(null);
    setTouched(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateProject((p) => {
    close();
    const c = p.channels[0];
    if (c) setChannel(p.id, c.id);
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!projects) { setNameErr("Still loading projects — try again in a moment."); return; }
    const err = validate(name);
    setNameErr(err);
    if (err) return;
    create.mutate({ name: toSlug(name), description: description.trim() || undefined });
  };
  return (
    <Dialog
      open={open}
      onClose={close}
      title="New project"
      description="A project groups channels, chats, and the AI personas that work in them."
      icon={<FolderPlus size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="wp-form" size="sm" variant="primary" loading={create.isPending}>Create project</Button>
        </div>
      }
    >
      <form id="wp-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="pname" required>Name</Label>
          <Input
            id="pname"
            required
            autoFocus
            placeholder="e.g. Quarterly Review"
            value={name}
            maxLength={60}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validate(e.target.value));
            }}
            onBlur={() => {
              setTouched(true);
              setNameErr(validate(name));
            }}
          />
          <FieldError>{nameErr}</FieldError>
        </div>
        <div>
          <Label htmlFor="pdesc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="pdesc" placeholder="What is this project about?" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
          <p className="mt-1.5 text-[12px] text-ink2">Helps teammates — and AI personas — understand the project&apos;s purpose.</p>
        </div>
      </form>
    </Dialog>
  );
}

function CreateChannelDialog({ projectId, projectName, existingNames, open, onClose }: {
  projectId: string;
  projectName: string;
  existingNames: string[];
  open: boolean;
  onClose: () => void;
}) {
  const { setChannel } = useSelection();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Channels are stored under a kebab-cased name — compare the normalized form,
  // not the raw typed string (see the project dialog for the same reasoning).
  const toSlug = (v: string) => v.trim().toLowerCase().replace(/\s+/g, "-");
  const validate = (v: string): string | null => {
    const base = validateName(v, { label: "channel name", max: 40 });
    if (base) return base;
    const s = toSlug(v);
    if (existingNames.some((n) => n.toLowerCase() === s)) return `A channel named "${v.trim()}" already exists.`;
    return null;
  };
  const reset = () => {
    setName("");
    setDescription("");
    setNameErr(null);
    setTouched(false);
  };
  const close = () => {
    reset();
    onClose();
  };
  const create = useCreateChannel(projectId, (c) => {
    close();
    setChannel(projectId, c.id);
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    const err = validate(name);
    setNameErr(err);
    if (err) return;
    create.mutate({ name: toSlug(name), description: description.trim() || undefined });
  };
  return (
    <Dialog
      open={open}
      onClose={close}
      title={`New channel in ${projectName}`}
      description="Channels split a project by subject — like #engineering or #marketing. Chats live inside them."
      icon={<Hash size={17} strokeWidth={2} />}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}>Cancel</Button>
          <Button type="submit" form="wc-form" size="sm" variant="primary" loading={create.isPending}>Create channel</Button>
        </div>
      }
    >
      <form id="wc-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
        <div>
          <Label htmlFor="cname" required>Name</Label>
          <Input
            id="cname"
            required
            autoFocus
            placeholder="e.g. backend"
            value={name}
            maxLength={40}
            aria-invalid={!!nameErr}
            onChange={(e) => {
              setName(e.target.value);
              if (touched) setNameErr(validate(e.target.value));
            }}
            onBlur={() => {
              setTouched(true);
              setNameErr(validate(name));
            }}
          />
          {nameErr ? <FieldError>{nameErr}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Short and lowercase reads best — it becomes #{name.trim().toLowerCase().replace(/\s+/g, "-") || "channel-name"}.</p>}
        </div>
        <div>
          <Label htmlFor="cdesc">Description <span className="text-ink2">(optional)</span></Label>
          <Input id="cdesc" placeholder="What belongs in this channel?" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
        </div>
      </form>
    </Dialog>
  );
}
