"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { ProfileDialog } from "@/components/shell/profile-dialog";
import { ConfirmDialog } from "@/components/ui/dialog";
import { absolutizeMedia } from "@/lib/api/client";
import { useMembers } from "@/hooks/use-workspace";
import { clearAccountScopedState } from "@/lib/auth/session-cleanup";
import { supabase } from "@/lib/supabase";
import { useConnectionStore } from "@/stores/connection.store";

// The avatar button + account menu (Profile / Sign out) + profile dialog +
// sign-out confirmation, used in the workspace top bar. Clicking the avatar
// opens a menu rather than jumping straight into the dialog.
export function ProfileButton({ size = 9 }: { size?: 8 | 9 }) {
  const router = useRouter();
  const { email, connection } = useConnectionStore();
  const { data: members } = useMembers();
  const avatar = absolutizeMedia(members?.find((m) => m.user_id === connection?.nucleusUserId)?.avatar ?? null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const signOut = async () => {
    clearAccountScopedState(); // one shared cleanup — stores, drafts, query cache, realtime
    try {
      await supabase().auth.signOut();
    } catch {
      /* local state is cleared regardless — the session dies on this device */
    }
    router.replace("/login");
  };

  // Close on outside click / Escape, and focus the first item on open. Depends
  // only on `menuOpen`, so focus moves on the open transition — never per render.
  useEffect(() => {
    if (!menuOpen) return;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const onMenuKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Tab") return setMenuOpen(false); // let focus leave naturally
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]')];
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
    items[next]?.focus();
  };

  const item = "flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] transition-colors hover:bg-surface2 focus:bg-surface2 focus:outline-none";

  return (
    <div ref={wrapRef} className="relative">
      <button
        ref={btnRef}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        title={email ?? undefined}
        onClick={() => setMenuOpen((o) => !o)}
        className={`flex ${size === 8 ? "size-8 text-[12px]" : "size-9 text-[13px]"} items-center justify-center overflow-hidden rounded-full bg-accent font-bold text-accent-ink ring-1 ring-line transition-shadow hover:ring-accent`}
      >
        {avatar ? (
          // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
          <img src={avatar} alt="" className="size-full object-cover" />
        ) : (
          (email ?? "?")[0]?.toUpperCase()
        )}
      </button>
      {menuOpen && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 top-full z-50 mt-2 w-56 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-lg"
        >
          {email && (
            <div className="truncate border-b border-line px-3 pb-2 pt-1 text-[12px] text-ink2">
              Signed in as <span className="font-medium text-ink">{email}</span>
            </div>
          )}
          <button role="menuitem" className={`${item} text-ink`} onClick={() => { setMenuOpen(false); setProfileOpen(true); }}>
            <User size={15} strokeWidth={2} className="flex-none text-ink2" /> Profile
          </button>
          <button role="menuitem" className={`${item} text-crit`} onClick={() => { setMenuOpen(false); setConfirmingSignOut(true); }}>
            <LogOut size={15} strokeWidth={2} className="flex-none" /> Sign out
          </button>
        </div>
      )}
      <ProfileDialog
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        onSignOut={() => {
          setProfileOpen(false);
          setConfirmingSignOut(true);
        }}
      />
      <ConfirmDialog
        open={confirmingSignOut}
        onClose={() => setConfirmingSignOut(false)}
        onConfirm={() => {
          setConfirmingSignOut(false);
          void signOut();
        }}
        title="Sign out?"
        body={<p>You&apos;ll be signed out of <b className="text-ink">{email}</b> on this device. Your saved servers stay with your account — they&apos;ll be back when you sign in again.</p>}
        confirmLabel="Sign out"
        confirmIcon={<LogOut size={14} strokeWidth={2} />}
        tone="neutral"
      />
    </div>
  );
}
