"use client";

import { useEffect, useState } from "react";
import { PanelLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { AboutDialog } from "@/components/shell/about-dialog";
import { CommandPalette } from "@/components/shell/command-palette";
import { TopBar } from "@/components/shell/top-bar";
import { WorkspaceTree } from "@/components/shell/workspace-tree";
import { FullPageLoader } from "@/components/ui/full-page-loader";
import { useConnectionStore } from "@/stores/connection.store";
import { useSelection } from "@/stores/selection.store";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { token, serverUrl, hydrated } = useConnectionStore();
  const [about, setAbout] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const { sel } = useSelection();

  // The /servers redirect must wait for zustand PERSIST to restore serverUrl —
  // not just Supabase's `hydrated`. A warm session sets hydrated+token before
  // persist rehydrates serverUrl, which otherwise bounces us to /servers on a
  // refresh (the race the user saw). Track persist hydration separately.
  const [persistReady, setPersistReady] = useState(false);
  useEffect(() => {
    // hasHydrated()/onFinishHydration are client-only (never call in the lazy
    // initializer — it runs during SSR prerender and throws). Already-hydrated
    // path defers the setState via rAF (no setState directly in an effect).
    const mark = () => setPersistReady(true);
    if (useConnectionStore.persist.hasHydrated()) {
      const raf = requestAnimationFrame(mark);
      return () => cancelAnimationFrame(raf);
    }
    return useConnectionStore.persist.onFinishHydration(mark);
  }, []);

  // Drawer closes when a destination is picked — not on expand/collapse taps.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMobileNav(false));
    return () => cancelAnimationFrame(raf);
  }, [sel?.cid, sel?.tid]);
  useEffect(() => {
    if (!mobileNav) return;
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && setMobileNav(false);
    document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [mobileNav]);

  useEffect(() => {
    if (!hydrated || !persistReady) return;
    if (!token) router.replace("/login");
    else if (!serverUrl) router.replace("/servers");
  }, [hydrated, persistReady, token, serverUrl, router]);

  // The persisted connection (role, company) can go stale — demoted-on-the-
  // server admins would keep seeing manage buttons forever. Re-verify once
  // per workspace mount; silent failure keeps the persisted state.
  useEffect(() => {
    if (!hydrated || !token || !serverUrl) return;
    void import("@/lib/api/servers").then(({ connectToServer }) =>
      connectToServer(serverUrl, token).then((out) => {
        if (out.kind === "ok") useConnectionStore.getState().connect(out.connection);
      }).catch(() => undefined),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount when authenticated
  }, [hydrated, !!token, serverUrl]);

  // Held behind hydration/auth: the same full-page loader every other page
  // uses — a lone skeleton here read as an empty box on every reload.
  if (!hydrated || !token || !serverUrl) {
    return <FullPageLoader />;
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <TopBar onAbout={() => setAbout(true)} />
      <div className="flex min-h-0 flex-1">
      {/* Workspace tree: inline ≥lg, drawer below */}
      <div className="hidden lg:flex">
        <WorkspaceTree />
      </div>
      {mobileNav && (
        <div className="fixed inset-0 z-40 flex lg:hidden" role="presentation">
          <div aria-hidden className="absolute inset-0 bg-black/55 backdrop-blur-[2px] motion-safe:animate-[nx-fade-in_.15s_ease-out]" onMouseDown={() => setMobileNav(false)} />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Workspace navigation"
            tabIndex={-1}
            ref={(el) => el?.focus()}
            className="relative flex h-full shadow-2xl outline-none motion-safe:animate-[nx-drawer-in_.2s_ease-out]"
          >
            <WorkspaceTree />
          </div>
        </div>
      )}
      <main className="flex min-w-0 flex-1 flex-col">
        <button
          className="m-2 flex items-center gap-2 self-start rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] text-ink2 lg:hidden"
          onClick={() => setMobileNav(true)}
          aria-label="Open navigation"
        >
          <PanelLeft size={15} strokeWidth={2} /> Workspace
        </button>
        {children}
      </main>
      </div>
      <AboutDialog open={about} onClose={() => setAbout(false)} />
      <CommandPalette onAbout={() => setAbout(true)} />
    </div>
  );
}
