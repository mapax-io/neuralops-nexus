import { apiJson } from "./client";

export interface Member {
  user_id: string;
  email: string;
  role: string;
  invited_by: string | null;
  joined_at: string;
  avatar: string | null;
}

export const listMembers = () => apiJson<Member[]>(`/api/v1/members/`);

// A project to add the invitee to. Empty topic_ids = the whole project (a
// project-scope role, reaching topics created later); ids = only those topics.
export interface Grant {
  project_id: string;
  topic_ids: string[];
}

export interface InviteResult {
  ok: boolean;
  message: string;
  email: string;
  role: string;
  // True when the server created a pending Invitation (nobody with this
  // email yet) — only that outcome also carries expires_at. No email is sent.
  is_new_user?: boolean;
  expires_at?: string | null;
  // A server holding its identity project's service key also emails the
  // invitee; email_note says why not otherwise (address already registered…).
  email_sent?: boolean;
  email_note?: string | null;
  // Echoed by a server that understood `grants`; absent on one that silently
  // ignored the field — which is how the client tells the two apart.
  grants?: Grant[];
}

// Where the invitation email should land the invitee: the app's own reset
// page, where they set a password. Must be on the project's redirect list.
export const inviteRedirectTo = () => `${window.location.origin}/reset-password`;

// Server checks the add_invitation permission; 403 surfaces as a toast. With
// grants, the role lands on those projects/topics only; without, server-wide.
export const inviteMember = (email: string, role: string, grants: Grant[] = [], redirectTo: string = inviteRedirectTo()) =>
  apiJson<InviteResult>(`/api/v1/members/invite/`, {
    method: "POST",
    body: JSON.stringify({ email, role, redirect_to: redirectTo, ...(grants.length ? { grants } : {}) }),
  });

// What a member holds, in the invite's own shape: a server-wide role, or the
// projects/topics they are scoped to.
export interface MemberAccess {
  user_id: string;
  role: string;
  server_wide: boolean;
  grants: Grant[];
}

export const getMemberAccess = (userId: string) => apiJson<MemberAccess>(`/api/v1/members/${userId}/access/`);

// Full replace, same rule as an invite: no grants = server-wide at `role`;
// otherwise exactly those, at `role`. Server refuses the owner and yourself.
export const setMemberAccess = (userId: string, body: { role: string; grants: Grant[] }) =>
  apiJson<MemberAccess>(`/api/v1/members/${userId}/access/`, { method: "PUT", body: JSON.stringify(body) });

// Server rules: cannot remove the owner or yourself; Admin+ only.
export const removeMember = (userId: string) =>
  apiJson<{ ok: boolean; message: string }>(`/api/v1/members/${userId}/`, { method: "DELETE" });
