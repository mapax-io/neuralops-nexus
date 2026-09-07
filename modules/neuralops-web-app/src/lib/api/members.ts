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

export interface InviteResult {
  ok: boolean;
  message: string;
  email: string;
  role: string;
  // True when the server created a pending Invitation (nobody with this
  // email yet) — only that outcome also carries expires_at. No email is sent.
  is_new_user?: boolean;
  expires_at?: string | null;
}

// Server checks the add_invitation permission; 403 surfaces as a toast.
export const inviteMember = (email: string, role: string) =>
  apiJson<InviteResult>(`/api/v1/members/invite/`, { method: "POST", body: JSON.stringify({ email, role }) });

// Server rules: cannot remove the owner or yourself; Admin+ only.
export const removeMember = (userId: string) =>
  apiJson<{ ok: boolean; message: string }>(`/api/v1/members/${userId}/`, { method: "DELETE" });
