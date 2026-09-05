"use client";

import { usePathname, useRouter } from "next/navigation";
import { ArrowLeftRight, Bot, Cpu, Info, Plug2, Search, UserRound, Users } from "lucide-react";
import { NexusMark } from "@/components/brand/wordmark";
import { ThemeToggle } from "@/components/theme-toggle";
import { ProfileButton } from "@/components/shell/profile-button";
import { teardownRealtime } from "@/lib/realtime/centrifugo";
import { useSearchShortcut } from "@/lib/platform";
import { useConnectionStore } from "@/stores/connection.store";
import { useUiStore } from "@/stores/ui.store";

// THE app chrome: one fixed top bar on every workspace route — the app mark
// (home), quick actions, intelligence quick-launch with live active states,
// the ⌘K search front-and-center, and identity on the right. Nothing is
// duplicated elsewhere: this bar replaced the old left icon rail.
export function TopBar({ onAbout }: { onAbout: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const companyName = useConnectionStore((s) => s.connection?.companyName);
  const disconnect = useConnectionStore((s) => s.disconnect);
  const intelSection = useUiStore((u) => u.intelSection);
  const setIntelSection = useUiStore((u) => u.setIntelSection);
  const shortcut = useSearchShortcut();

  const onWorkspace = pathname?.startsWith("/w") ?? false;
  const onIntel = pathname?.startsWith("/intelligence") ?? false;

  const openPalette = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
  const intel = (section: string) => {
    setIntelSection(section);
    router.push("/intelligence");
  };

  return (
    <div className="flex h-12 flex-none items-center gap-1 border-b border-line bg-bg2 px-3">
      {/* The app mark + workspace name ARE the home button. Names up to the
          50ch render cap show IN FULL; only beyond it (or when the bar runs
          out of room) does the name clip — never the layout. Below lg it
          hides here and the nav drawer's header shows it instead (wrapping,
          uncapped) — the two visibilities are exact complements. */}
      <button
        aria-label={companyName ?? "Workspace"}
        title={companyName ?? "Workspace"}
        onClick={() => {
          // Always land back on the workspace where you left off — never clear
          // the open chat (that footgun dumped users on the empty home).
          if (!onWorkspace) router.push("/w");
        }}
        className="mr-1 flex h-8 min-w-0 shrink items-center gap-2 rounded-lg px-1 transition-colors hover:bg-surface"
      >
        <NexusMark className="size-7 flex-none" />
        <span className="hidden max-w-[50ch] min-w-0 truncate font-display text-[14px] font-bold lg:block">{companyName ?? "Workspace"}</span>
      </button>
      <span aria-hidden className="mx-1.5 hidden h-5 w-px bg-line sm:block" />
      {/* Intelligence quick-launch — straight to the section, lit when there. */}
      <div className="hidden items-center gap-1 sm:flex">
        <BarButton label="Personas" text="Personas" active={onIntel && intelSection === "personas"} onClick={() => intel("personas")}><UserRound size={16} strokeWidth={1.9} /></BarButton>
        <BarButton label="AI models" text="Models" active={onIntel && intelSection === "models"} onClick={() => intel("models")}><Cpu size={16} strokeWidth={1.9} /></BarButton>
        <BarButton label="MCP servers" text="MCP" active={onIntel && intelSection === "mcp"} onClick={() => intel("mcp")}><Plug2 size={16} strokeWidth={1.9} /></BarButton>
        <BarButton label="Agents" text="Agents" active={onIntel && intelSection === "agents"} onClick={() => intel("agents")}><Bot size={16} strokeWidth={1.9} /></BarButton>
        <BarButton label="Members" text="Members" active={pathname?.startsWith("/members") ?? false} onClick={() => router.push("/members")}><Users size={16} strokeWidth={1.9} /></BarButton>
      </div>

      {/* The search pill IS the palette — one muscle memory, two entry points. */}
      <div className="flex min-w-0 flex-1 justify-center px-2">
        <button
          onClick={openPalette}
          aria-label={`Search the workspace (${shortcut})`}
          className="flex h-8 w-full max-w-xl items-center gap-2.5 rounded-lg border border-line bg-surface px-3 text-left text-[13px] text-ink2 transition-colors hover:border-accent/50 hover:text-ink"
        >
          <Search size={14} strokeWidth={2} className="flex-none" />
          <span className="min-w-0 flex-1 truncate">Search projects, channels &amp; chats…</span>
          <kbd className="hidden flex-none rounded border border-line bg-surface2 px-1.5 font-mono text-[10.5px] sm:block">{shortcut}</kbd>
        </button>
      </div>

      <div className="flex items-center gap-1">
        <ThemeToggle />
        <BarButton label="About NeuralOps Nexus" onClick={onAbout}>
          <Info size={17} strokeWidth={1.9} />
        </BarButton>
        <BarButton
          label="Switch server"
          onClick={() => {
            teardownRealtime();
            disconnect();
            router.push("/servers");
          }}
        >
          <ArrowLeftRight size={17} strokeWidth={1.9} />
        </BarButton>
        <span aria-hidden className="mx-1 hidden h-5 w-px bg-line sm:block" />
        <ProfileButton size={8} />
      </div>
    </div>
  );
}

function BarButton({ label, text, onClick, disabled, active, children }: {
  label: string;
  text?: string; // short visible label; icon-only when omitted
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      aria-current={active ? "page" : undefined}
      disabled={disabled}
      onClick={onClick}
      className={`flex h-8 flex-none cursor-pointer items-center justify-center gap-1.5 rounded-lg border transition-colors disabled:cursor-default disabled:opacity-35 ${
        text ? "px-2.5" : "w-8"
      } ${
        active
          ? "border-accent/30 bg-accent/10 text-accent"
          : "border-transparent text-ink2 hover:bg-surface hover:text-ink"
      }`}
    >
      {children}
      {text && <span className="hidden text-[13px] font-medium md:inline">{text}</span>}
    </button>
  );
}
