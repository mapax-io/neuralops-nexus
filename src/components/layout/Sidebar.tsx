import { Link, useRouterState } from "@tanstack/react-router";
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
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth.store";
import { signOut } from "@/services/auth.service";
import { useNavigate } from "@tanstack/react-router";

// Placeholder static tree — wired to real services in a later prompt.
const MOCK_TREE = [
  {
    id: "p1",
    name: "Acme AI Ops",
    channels: [
      {
        id: "c1",
        name: "general",
        topics: [
          { id: "t1", title: "Welcome to NeuralOps" },
          { id: "t2", title: "Roadmap" },
        ],
      },
      { id: "c2", name: "incidents", topics: [] },
    ],
  },
];

export function Sidebar() {
  const navigate = useNavigate();
  const email = useAuthStore((s) => s.email);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const path = useRouterState({ select: (s) => s.location.pathname });

  const [openProjects, setOpenProjects] = useState<Record<string, boolean>>({
    p1: true,
  });
  const [openChannels, setOpenChannels] = useState<Record<string, boolean>>({
    c1: true,
  });

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
          <div className="truncate text-xs text-foreground-muted">Acme Workspace</div>
        </div>
        <Button size="icon" variant="ghost" aria-label="Switch company">
          <ChevronDown className="h-4 w-4" />
        </Button>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 border-b border-sidebar-border p-2">
        <SidebarLink to="/app" exact label="Workspace" icon={<MessageSquare className="h-4 w-4" />} active={path === "/app"} />
        <SidebarLink to="/app/agents" label="Agents" icon={<Hash className="h-4 w-4" />} active={path.startsWith("/app/agents")} />
        <SidebarLink to="/app/knowledge" label="Knowledge" icon={<Folder className="h-4 w-4" />} active={path.startsWith("/app/knowledge")} />
      </nav>

      {/* Project tree */}
      <div className="flex-1 overflow-y-auto p-2">
        <div className="mb-2 flex items-center justify-between px-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Projects
          </span>
          <button className="text-foreground-muted hover:text-foreground" aria-label="Add project">
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {MOCK_TREE.map((project) => {
          const popen = openProjects[project.id] ?? false;
          return (
            <div key={project.id} className="mb-2">
              <button
                onClick={() =>
                  setOpenProjects((o) => ({ ...o, [project.id]: !popen }))
                }
                className="flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent"
              >
                {popen ? (
                  <ChevronDown className="h-3.5 w-3.5 text-foreground-muted" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-foreground-muted" />
                )}
                <Folder className="h-3.5 w-3.5 text-foreground-muted" />
                <span className="truncate">{project.name}</span>
                <Plus className="ml-auto h-3 w-3 text-foreground-muted" />
              </button>

              {popen && (
                <div className="ml-3 mt-1 border-l border-sidebar-border pl-2">
                  {project.channels.map((channel) => {
                    const copen = openChannels[channel.id] ?? false;
                    return (
                      <div key={channel.id} className="mb-1">
                        <button
                          onClick={() =>
                            setOpenChannels((o) => ({
                              ...o,
                              [channel.id]: !copen,
                            }))
                          }
                          className="flex w-full items-center gap-1 rounded-md px-2 py-1 text-sm text-foreground-muted hover:bg-sidebar-accent hover:text-foreground"
                        >
                          {copen ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                          <Hash className="h-3 w-3" />
                          <span className="truncate">{channel.name}</span>
                          <Plus className="ml-auto h-3 w-3" />
                        </button>

                        {copen && (
                          <div className="ml-3 mt-0.5 flex flex-col gap-0.5">
                            {channel.topics.map((t) => (
                              <button
                                key={t.id}
                                className="truncate rounded-md px-2 py-1 text-left text-xs text-foreground-muted hover:bg-sidebar-accent hover:text-foreground"
                              >
                                {t.title}
                              </button>
                            ))}
                            {channel.topics.length === 0 && (
                              <div className="px-2 py-1 text-xs text-foreground-muted">
                                No topics yet
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-1 border-t border-sidebar-border p-2">
        <Button size="icon" variant="ghost" aria-label="Notifications">
          <Bell className="h-4 w-4" />
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
    </aside>
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
