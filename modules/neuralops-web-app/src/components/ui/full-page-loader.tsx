"use client";

import { useEffect, useState } from "react";
import { NexusMark } from "@/components/brand/wordmark";
import { Button } from "@/components/ui/button";
import { signOutOnThisDevice } from "@/lib/auth/sign-out";

// Past this, a page held behind hydration/auth is stuck, not loading.
const SLOW_AFTER_MS = 10_000;

// Full-screen loader for blank pages — a route/segment loading, or a page held
// behind hydration/auth. Shows the app mark so an empty page never just sits
// there as a bare box — and never sits there forever: after a while it says
// so and offers a way out, because "clear site data and sign in again" is
// not something anyone should have to work out for themselves.
export function FullPageLoader({ label = "Loading…", escape }: {
  label?: string;
  // Hard navigations on purpose: a fresh document also sheds a stale build.
  escape?: { reload: () => void; signOut: () => Promise<void> };
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => window.clearTimeout(t);
  }, []);
  const reload = escape?.reload ?? (() => window.location.reload());
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a hard navigation on purpose: a fresh document also sheds a stale build
  const signOut = escape?.signOut ?? (() => signOutOnThisDevice().finally(() => window.location.assign("/login")));

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg" role="status" aria-label={label}>
      <div className="flex flex-col items-center gap-3">
        <NexusMark className="size-10 animate-pulse" />
        <span className="text-[13px] text-ink2">{label}</span>
        {slow && (
          <div className="mt-3 flex flex-col items-center gap-2 text-center">
            <p className="text-[12.5px] text-ink2">This is taking longer than usual.</p>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={reload}>Reload</Button>
              <Button size="sm" variant="link" onClick={() => void signOut()}>Sign out</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
