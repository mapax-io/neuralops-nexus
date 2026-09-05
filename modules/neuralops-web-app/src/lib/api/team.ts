import { apiJson } from "./client";

// The /invite slash command's endpoint (DECISIONS §13): persona OR email,
// project scope by default, optionally narrowed to one topic. This is an
// upstream endpoint; the composer's /invite command is its only caller.
export const inviteToProject = (
  pid: string,
  body: { email?: string; persona_name?: string; scope: "project" | "topic"; topic_id?: string; role?: string },
) => apiJson<{ ok: boolean; message: string; invite_url?: string | null }>(
  `/api/v1/projects/${pid}/team/invite/`,
  { method: "POST", body: JSON.stringify(body) },
);

// ── Project team roster (parity with the classic app's "Add to Team") ──
// Plain membership only — people are added as "member"; there is no role
// editing here (roles/permissions management is deliberately out of scope).

export interface TeamMember {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  member_type: "human" | "persona";
  avatar?: string | null;
}
export interface AvailableUser { user_id: string; name: string; email: string; avatar?: string | null }
// No backing details here — the server dropped source_type with the agent
// collapse; join on persona_id with the project persona list for those.
export interface AvailablePersona { persona_id: string; user_id: string; name: string; avatar?: string | null }

const base = (pid: string) => `/api/v1/projects/${pid}/team/`;

export const listTeam = (pid: string) => apiJson<TeamMember[]>(base(pid));

export const listAvailableUsers = (pid: string, search = "") =>
  apiJson<AvailableUser[]>(`${base(pid)}available-users/${search ? `?search=${encodeURIComponent(search)}` : ""}`);

export const listAvailablePersonas = (pid: string) =>
  apiJson<AvailablePersona[]>(`${base(pid)}available-personas/`);

export const addTeamMember = (pid: string, userId: string) =>
  apiJson<TeamMember>(base(pid), { method: "POST", body: JSON.stringify({ user_id: userId, role: "member" }) });

export const removeTeamMember = (pid: string, userId: string) =>
  apiJson<{ ok: boolean; message?: string }>(`${base(pid)}${userId}/`, { method: "DELETE" });
