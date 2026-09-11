"use client";

import { toast } from "sonner";
import { copyText } from "@/lib/browser";
import { inviteInstructions, isPendingInvite, type InviteOutcome } from "@/lib/invite-copy";

// One outcome toast for every invite entry point (members page, members
// dialog, the /invite command). A pending invite never talks about email:
// whether the server managed to send one is not the inviter's concern -- the
// way in is the same either way, and the steps are theirs to pass on. So the
// toast stays until they copy the steps or close it themselves.
export function notifyInvite(
  r: InviteOutcome & { email: string; message?: string },
  ctx: { serverUrl: string | null | undefined; appOrigin: string; companyName?: string | null },
): void {
  if (!isPendingInvite(r)) {
    toast.success(r.message || `${r.email} added to this server.`);
    return;
  }
  const steps = inviteInstructions({ email: r.email, appOrigin: ctx.appOrigin, serverUrl: ctx.serverUrl, companyName: ctx.companyName, expiresAt: r.expires_at });
  const id = toast.success(`${r.email} is invited.`, {
    description: "They sign up with that exact address, add this server, and they're in with the access you gave them.",
    duration: Infinity,
    closeButton: true,
    action: {
      label: "Copy steps",
      onClick: (event) => {
        // sonner closes a toast on any action click; this one closes only
        // once the steps are actually on the clipboard.
        event.preventDefault();
        void copyText(steps).then((ok) => {
          if (ok) {
            toast.dismiss(id);
            toast.success("Steps copied — send them along.");
          } else {
            toast.error("Couldn't copy the steps.");
          }
        });
      },
    },
  });
}
