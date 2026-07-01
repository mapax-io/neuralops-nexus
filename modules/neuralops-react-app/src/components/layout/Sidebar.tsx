import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Plus,
  MessageSquare,
  Hash,
  Folder,
  Bell,
  Settings,
  LogOut,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
import { signOut } from "@/services/auth.service";
import { MembersPanel } from "@/components/members/MembersPanel";
import { useProjects } from "@/hooks/useWorkspace";
import { AddProjectDialog } from "@/components/workspace/AddProjectDialog";
import { AddChannelDialog } from "@/components/workspace/AddChannelDialog";
import type { Project, Channel } from "@/services/workspace.service";

export function Sidebar() {
  const navigate = useNavigate();
  const email = useAuthStore((s) => s.email);
  const role = useAuthStore((s) => s.role);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const path = useRouterState({ select: (s) => s.location.pathname });

  const canManage = role === "owner" || role === "admin";

  const { data: projects, isLoading } = useProjects();

  const [openProjects, setOpenProjects] = useState<Record<string, boolean>>({});
  const [membersOpen, setMembersOpen] = useState(false);
  const [addProjectOpen, setAddProjectOpen] = useState(false);
  const [addChannelFor, setAddChannelFor] = useState<string | null>(null);

  async function handleSignOut() {
    try {
      await signOut();
    } catch {
      /* ignore */
    }
    clearAuth();
    navigate({ to: "/" });
  }

  return (
    <aside
      className="flex h-screen w-[260px] flex-col border-r border-sidebar-border bg-sidebar"
      data-component="Sidebar"
    >
      {/* Company switcher */}
      <div className="flex items-center gap-2 border-b border-sidebar-border px-3 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Building2 className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">NeuralOps</div>
          <div className="truncate text-xs text-foreground-muted">
            Acme Workspace
          </div>
        </div>
        <Button size="icon" variant="ghost" aria-label="Switch company">
          <ChevronDown className="h-4 w-4" />
        </Button>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 border-b border-sidebar-border p-2">
        <SidebarLink
          to="/app"
          exact
          label="Workspace"
          icon={<MessageSquare className="h-4 w-4" />}
          active={path === "/app"}
        />
        <SidebarLink
          to="/app/agents"
          label="Agents"
          icon={<Hash className="h-4 w-4" />}
          active={path.startsWith("/app/agents")}
        />
        <SidebarLink
          to="/app/knowledge"
          label="Knowledge"
          icon={<Folder className="h-4 w-4" />}
          active={path.startsWith("/app/knowledge")}
        />
      </nav>

      {/* Project tree */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="mb-2 flex items-center justify-between px-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Projects
          </span>
          {canManage && (
            <button
              className="text-foreground-muted hover:text-foreground"
              aria-label="Add project"
              onClick={() => setAddProjectOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {isLoading && (
          <div className="space-y-2 px-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        )}

        {!isLoading && projects && projects.length === 0 && (
          <div className="flex flex-col items-start gap-2 px-2 py-4">
            <p className="text-xs text-foreground-muted">No projects yet</p>
            {canManage && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setAddProjectOpen(true)}
              >
                Create your first project
              </Button>
            )}
          </div>
        )}

        {!isLoading &&
          projects?.map((project) => {
            const popen = openProjects[project.id] ?? false;
            return (
              <ProjectNode
                key={project.id}
                project={project}
                open={popen}
                onToggle={() =>
                  setOpenProjects((o) => ({ ...o, [project.id]: !popen }))
                }
                canManage={canManage}
                onAddChannel={() => setAddChannelFor(project.id)}
              />
            );
          })}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-1 border-t border-sidebar-border p-2">
        <Button size="icon" variant="ghost" aria-label="Notifications">
          <Bell className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Members"
          onClick={() => setMembersOpen(true)}
        >
          <Users className="h-4 w-4" />
        </Button>
        <Link
          to="/app/settings"
          className="inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-sidebar-accent"
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </Link>
        <div className="ml-1 flex min-w-0 flex-1 items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-tint text-xs font-medium text-primary">
            {(email ?? "?").slice(0, 1).toUpperCase()}
          </div>
          <div className="truncate text-xs text-foreground-muted">{email}</div>
        </div>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Sign out"
          onClick={handleSignOut}
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>

      {/* Sheets & Dialogs */}
      <Sheet open={membersOpen} onOpenChange={setMembersOpen}>
        <SheetContent side="right" className="w-[420px] p-0">
          <SheetHeader className="px-4 py-3 border-b">
            <SheetTitle>Server Members</SheetTitle>
          </SheetHeader>
          <div className="p-4">
            <MembersPanel />
          </div>
        </SheetContent>
      </Sheet>

      <AddProjectDialog
        open={addProjectOpen}
        onOpenChange={setAddProjectOpen}
      />

      {addChannelFor && (
        <AddChannelDialog
          open={!!addChannelFor}
          onOpenChange={(o) => !o && setAddChannelFor(null)}
          projectId={addChannelFor}
        />
      )}
    </aside>
  );
}

function ProjectNode({
  project,
  open,
  onToggle,
  canManage,
  onAddChannel,
}: {
  project: Project;
  open: boolean;
  onToggle: () => void;
  canManage: boolean;
  onAddChannel: () => void;
}) {
  return (
    <div className="mb-2">
      <div className="group flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent">
        <button onClick={onToggle} className="flex flex-1 items-center gap-1">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-foreground-muted" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-foreground-muted" />
          )}
          <Folder className="h-3.5 w-3.5 text-foreground-muted" />
          <span className="truncate">{project.name}</span>
        </button>
        {canManage && (
          <button
            aria-label="Add channel"
            className="ml-auto text-foreground-muted opacity-0 hover:text-foreground group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation();
              onAddChannel();
            }}
          >
            <Plus className="h-3 w-3" />
          </button>
        )}
      </div>

      {open && (
        <div className="ml-3 mt-1 border-l border-sidebar-border pl-2">
          {project.channels.length === 0 && (
            <div className="px-2 py-1 text-xs text-foreground-muted">
              No channels yet
            </div>
          )}
          {project.channels.map((channel) => (
            <ChannelNode
              key={channel.id}
              projectId={project.id}
              channel={channel}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ChannelNode({
  projectId,
  channel,
}: {
  projectId: string;
  channel: Channel;
}) {
  const activeChannelId = useUIStore((s) => s.activeChannelId);
  const setActiveTopic = useUIStore((s) => s.setActiveTopic);
  const active = activeChannelId === channel.id;

  return (
    <button
      onClick={() => setActiveTopic(projectId, channel.id, "")}
      className={`flex w-full items-center gap-1 rounded-md px-2 py-1 text-sm ${
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
          : "text-foreground-muted hover:bg-sidebar-accent hover:text-foreground"
      }`}
    >
      <Hash className="h-3 w-3 shrink-0" />
      <span className="truncate">{channel.name}</span>
    </button>
  );
}

function SidebarLink({
  to,
  label,
  icon,
  active,
  exact,
}: {
  to: string;
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  exact?: boolean;
}) {
  return (
    <Link
      to={to}
      activeOptions={{ exact }}
      className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
          : "text-foreground-muted hover:bg-sidebar-accent hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </Link>
  );
}
