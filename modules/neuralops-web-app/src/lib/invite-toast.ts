"use client";

import { toast } from "sonner";
import { copyText } from "@/lib/browser";
import { inviteInstructions, isPendingInvite, type InviteOutcome } from "@/lib/invite-copy";

// One outcome toast for every invite entry point (members page, members
// dialog, the /invite command). A pending invite is honest about the fact
// that no email went out and hands the inviter the steps to pass on.
export function notifyInvite(
  r: InviteOutcome & { email: string; message?: string },
  ctx: { serverUrl: string | null | undefined; appOrigin: string; companyName?: string | null },
): void {
  if (!isPendingInvite(r)) {
    toast.success(r.message || `${r.email} added to this server.`);
    return;
  }
  if (r.email_sent) {
    toast.success(`Invitation email sent to ${r.email}.`, {
      description: "They set a password from the email, find this server on their launcher, and connect.",
      duration: 8_000,
    });
    return;
  }
  const steps = inviteInstructions({ email: r.email, appOrigin: ctx.appOrigin, serverUrl: ctx.serverUrl, companyName: ctx.companyName, expiresAt: r.expires_at });
  toast.success(`${r.email} is pre-authorised — no email went out, so pass the steps on.`, {
    description: r.email_note ?? "They create an account with that exact address, add this server, and connect.",
    duration: 30_000,
    action: {
      label: "Copy steps",
      onClick: () => void copyText(steps).then((ok) => (ok ? toast.success("Steps copied — send them along.") : toast.error("Couldn't copy the steps."))),
    },
  });
}
