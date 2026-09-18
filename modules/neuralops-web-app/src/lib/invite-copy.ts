// Invitations are pre-authorisations: the server records the address and lets
// that account in, with the access it was given, the moment it connects. The
// server may or may not manage to email the invitee (it needs a service key
// for that), and by product decision the app never says which -- the way in
// is the same, so the inviter gets the steps to pass on either way. These
// helpers make that a copy, not a conversation.

export interface InviteOutcome {
  is_new_user?: boolean;
  expires_at?: string | null;
}

// A brand-new person: the server created a pending Invitation (and only that
// outcome carries an expiry).
export const isPendingInvite = (r: InviteOutcome): boolean => !!r.is_new_user || !!r.expires_at;

export function inviteInstructions({ email, appOrigin, serverUrl, companyName, expiresAt }: {
  email: string;
  appOrigin: string;
  serverUrl: string | null | undefined;
  companyName?: string | null;
  expiresAt?: string | null;
}): string {
  const where = companyName ? `${companyName} on NeuralOps Nexus` : "NeuralOps Nexus";
  const server = serverUrl ? serverUrl : "the server address";
  const lines = [
    `You're invited to ${where}.`,
    `1. Create an account at ${appOrigin}/login with ${email} — this exact address.`,
    `2. In the app, open Servers, add ${server}, and press Connect. You're in automatically.`,
  ];
  if (expiresAt) {
    const when = new Date(expiresAt);
    lines.push(`This invitation expires ${Number.isNaN(when.getTime()) ? "soon" : `on ${when.toLocaleDateString([], { dateStyle: "medium" })}`}.`);
  }
  return lines.join("\n");
}
