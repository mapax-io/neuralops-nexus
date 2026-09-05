"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AboutDialog } from "@/components/shell/about-dialog";
import { CommandPalette } from "@/components/shell/command-palette";
import { TopBar } from "@/components/shell/top-bar";
import { McpTab } from "@/components/intelligence/mcp-tab";
import { ModelsTab } from "@/components/intelligence/models-tab";
import { IntelNav, type IntelSection } from "@/components/intelligence/nav";
import { PersonasTab } from "@/components/intelligence/personas-tab";
import { FullPageLoader } from "@/components/ui/full-page-loader";
import { useConnectionStore } from "@/stores/connection.store";
import { useUiStore } from "@/stores/ui.store";

// The Intelligence area: everything that powers AI teammates. Static URL —
// no ids ever reach the address bar.
export default function IntelligencePage() {
  const router = useRouter();
  const { token, serverUrl, hydrated, connection } = useConnectionStore();
  const [about, setAbout] = useState(false);
  // Section state lives in the ui store — the top bar reads it for its
  // active states and writes it from the quick-launch icons.
  const rawSection = useUiStore((u) => u.intelSection);
  const setSection = useUiStore((u) => u.setIntelSection);
  const section: IntelSection = (["personas", "models", "mcp"] as const).includes(rawSection as IntelSection)
    ? (rawSection as IntelSection)
    : "personas";
  const canManage = connection?.role === "owner" || connection?.role === "admin";

  useEffect(() => {
    if (!hydrated) return;
    if (!token) router.replace("/login");
    else if (!serverUrl) router.replace("/servers");
  }, [hydrated, token, serverUrl, router]);

  if (!hydrated || !token || !serverUrl) {
    return (
      <FullPageLoader />
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <TopBar onAbout={() => setAbout(true)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
        <IntelNav section={section} onSection={setSection} />
        <main className="nx-ambient min-w-0 flex-1 overflow-y-auto p-4 lg:px-6 lg:py-5">
          {section === "personas" && <PersonasTab canManage={canManage} />}
          {section === "models" && <ModelsTab canManage={canManage} />}
          {section === "mcp" && <McpTab />}
        </main>
      </div>
      <AboutDialog open={about} onClose={() => setAbout(false)} />
      <CommandPalette onAbout={() => setAbout(true)} />
    </div>
  );
}
