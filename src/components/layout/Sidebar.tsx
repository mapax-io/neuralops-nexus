import { Link, useRouterState } from "@tanstack/react-router";
import {
  Bell,
  ChevronDown,
  ChevronRight,
  Plus,
  Settings,
  Users,
  Database,
  Bot,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth.store";

interface NavLink {
  to: string;
  label: string;
  icon: typeof Bot;
}

const NAV: NavLink[] = [
  { to: "/app", label: "Workspace", icon: Users },
  { to: "/app/agents", label: "Agents", icon: Bot },
  { to: "/app/knowledge", label: "Knowledge", icon: Database },
];

export function Sidebar() {
  const email = useAuthStore((s) => s.email);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [projectsOpen, setProjectsOpen] = useState(true);

  return (
    <aside className="flex h-screen w-[260px] shrink-0 flex-col border-r border-[color:var(--border)] bg-[color:var(--sidebar)]">
      <div className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-3">
        <button className="flex items-center gap-2 rounded-md px-2 py-1 text-sm font-medium hover:bg-[color:var(--muted)]">
          <div className="size-6 rounded bg-[color:var(--primary)]" />
          <span>NeuralOps</span>
          <ChevronDown className="size-4 text-[color:var(--foreground-muted)]" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        <div className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-[color:var(--primary-tint)] text-[color:var(--primary)] font-medium"
                    : "text-[color:var(--foreground)] hover:bg-[color:var(--muted)]"
                }`}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </div>

        <div className="mt-6">
          <button
            onClick={() => setProjectsOpen((v) => !v)}
            className="flex w-full items-center justify-between rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wider text-[color:var(--foreground-muted)] hover:bg-[color:var(--muted)]"
          >
            <span className="flex items-center gap-1">
              {projectsOpen ? (
                <ChevronDown className="size-3" />
              ) : (
                <ChevronRight className="size-3" />
              )}
              Projects
            </span>
            <Plus className="size-3.5" />
          </button>
          {projectsOpen && (
            <div className="mt-1 px-3 py-4 text-xs text-[color:var(--foreground-muted)]">
              No projects yet
            </div>
          )}
        </div>
      </nav>

      <div className="border-t border-[color:var(--border)] p-2">
        <div className="flex items-center justify-between gap-2">
          <Link
            to="/app/settings"
            className="flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-[color:var(--muted)]"
          >
            <div className="flex size-7 items-center justify-center rounded-full bg-[color:var(--primary-tint)] text-xs font-medium text-[color:var(--primary)]">
              {email?.[0]?.toUpperCase() ?? "U"}
            </div>
            <span className="truncate text-xs text-[color:var(--foreground-muted)]">
              {email ?? "Signed in"}
            </span>
          </Link>
          <Button variant="ghost" size="icon" className="size-8">
            <Bell className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" className="size-8" asChild>
            <Link to="/app/settings">
              <Settings className="size-4" />
            </Link>
          </Button>
        </div>
      </div>
    </aside>
  );
}
