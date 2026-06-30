import { apiRequest } from "./api.client";

export interface Member {
  user_id: string;
  email: string;
  role: "owner" | "admin" | "member" | "viewer";
  invited_by: string | null;
  joined_at: string;
}

export interface InvitePayload {
  email: string;
  role: "admin" | "member" | "viewer";
}

export async function getMembers(): Promise<Member[]> {
  const res = await apiRequest("/api/v1/members/");
  if (!res.ok) throw new Error("Failed to fetch members");
  return res.json();
}

export async function inviteMember(payload: InvitePayload): Promise<void> {
  const res = await apiRequest("/api/v1/members/invite/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail ?? data.message ?? "Failed to send invitation");
  }
}

export async function removeMember(userId: string): Promise<void> {
  const res = await apiRequest(`/api/v1/members/${userId}/`, { method: "DELETE" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to remove member");
  }
}
