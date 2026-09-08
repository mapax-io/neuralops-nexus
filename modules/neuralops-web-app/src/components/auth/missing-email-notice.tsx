"use client";

import { LogOut, MailWarning } from "lucide-react";
import { Button } from "@/components/ui/button";

// A signed-in session with no email address can never connect: nucleus
// identifies people by the email claim in the token and rejects a token
// without one. GitHub accounts with a private, unverified email are the
// common case — say so up front instead of a bare 401 per server.
export function MissingEmailNotice({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div role="alert" className="mb-5 rounded-xl border border-warn/40 bg-warn/10 p-4 text-[13px] text-ink">
      <p className="flex items-center gap-2 font-semibold"><MailWarning size={16} strokeWidth={2} className="text-warn" /> Your account has no email address</p>
      <p className="mt-1.5 text-ink2">
        NeuralOps servers identify you by email, so connecting can&apos;t work until your account has one. If you signed in
        with GitHub, make your email public (or verify it) on GitHub and sign in again — or create an account with an
        email and password.
      </p>
      <div className="mt-3">
        <Button size="sm" onClick={onSignOut}><LogOut size={14} strokeWidth={2} /> Sign out</Button>
      </div>
    </div>
  );
}
