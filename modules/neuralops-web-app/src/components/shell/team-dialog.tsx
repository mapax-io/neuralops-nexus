"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Plus, Trash2, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import { absolutizeMedia } from "@/lib/api/client";
import { listPersonas } from "@/lib/api/intelligence";
import {
  addTeamMember,
  listAvailablePersonas,
  listAvailableUsers,
  listTeam,
  removeTeamMember,
  type TeamMember,
} from "@/lib/api/team";
import { useConnectionStore } from "@/stores/connection.store";

// Per-project team roster (parity with the classic app's "Add to Team").
// Humans and personas who belong to THIS project; add an existing server
// member or a persona, or remove someone. Plain membership — no role editing.
export function TeamDialog({ pid, projectName, open, onClose, canManage = true }: {
  pid: string;
  projectName: string;
  open: boolean;
  onClose: () => void;
  canManage?: boolean; // false → read-only roster (no add/remove), still shows personas
}) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const qc = useQueryClient();
  const enabled = open && !!serverUrl && !!token && !!pid;
  const [tab, setTab] = useState<"people" | "personas">("people");
  const [removing, setRemoving] = useState<TeamMember | null>(null);

  const team = useQuery({ queryKey: ["team", serverUrl, pid], queryFn: () => listTeam(pid), enabled });
  const availUsers = useQuery({ queryKey: ["team-available-users", serverUrl, pid], queryFn: () => listAvailableUsers(pid), enabled });
  const availPersonas = useQuery({ queryKey: ["team-available-personas", serverUrl, pid], queryFn: () => listAvailablePersonas(pid), enabled });
  // Every persona usable in this project (mentionable here), whether or not
  // it's a formal team-member row — the user expects to see them in the roster.
  const projectPersonas = useQuery({ queryKey: ["personas", serverUrl, pid], queryFn: () => listPersonas(pid), enabled });

  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["team", serverUrl, pid] }),
      qc.invalidateQueries({ queryKey: ["team-available-users", serverUrl, pid] }),
      qc.invalidateQueries({ queryKey: ["team-available-personas", serverUrl, pid] }),
    ]);

  const add = useMutation({
    mutationFn: (userId: string) => addTeamMember(pid, userId),
    onSuccess: async (m) => { toast.success(`${m.name} added to ${projectName}.`); await invalidate(); },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (userId: string) => removeTeamMember(pid, userId),
    onSuccess: async (r) => { toast.success(r.message || "Removed from the project."); await invalidate(); },
    onError: (e) => toast.error(e.message),
  });

  // Humans come from the team roster; personas from the project persona list
  // (so a mentionable persona shows even if it was never added as a formal
  // member row). Deduped by the persona's shadow user id.
  const humans = (team.data ?? []).filter((m) => m.member_type !== "persona");
  const teamPersonaIds = new Set((team.data ?? []).filter((m) => m.member_type === "persona").map((m) => m.user_id));
  const personaRows: TeamMember[] = (projectPersonas.data ?? []).map((pp) => ({
    id: `persona:${pp.id}`,
    user_id: pp.id,
    name: pp.name,
    email: "",
    role: "persona",
    member_type: "persona" as const,
    avatar: pp.avatar ?? null,
  }));
  const roster = [...humans, ...(team.data ?? []).filter((m) => m.member_type === "persona"),
    ...personaRows.filter((r) => !teamPersonaIds.has(r.user_id))];
  // What backs an addable persona — its model and how many tool servers it
  // mounts — read from the project persona list already loaded above.
  const personaDetail = (personaId: string) => {
    const pp = projectPersonas.data?.find((x) => x.id === personaId);
    if (!pp?.model) return null; // also covers a server still on the pre-#99 contract
    const n = pp.mcp_servers?.length ?? 0;
    return n ? `${pp.model.name} · ${n} ${n === 1 ? "tool" : "tools"}` : pp.model.name;
  };
  const busy = add.isPending || remove.isPending;

  return (
    <>
      <Dialog open={open} onClose={onClose} size="lg" icon={<Users size={18} strokeWidth={2} />}
        title={`${projectName} · Team`}
        description="Who works in this project — teammates and the personas they can @mention here.">
        <div className="flex flex-col gap-4">
          {/* Roster */}
          <section>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink2">On this project</p>
            {team.isLoading ? (
              <div className="flex flex-col gap-2"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
            ) : roster.length === 0 ? (
              <p className="rounded-lg border border-line bg-surface2/50 px-3 py-3 text-[13px] text-ink2">Nobody on this project yet — add a teammate or a persona below.</p>
            ) : (
              <ul className="overflow-hidden rounded-xl border border-line bg-surface">
                {roster.map((m) => {
                  const avatar = absolutizeMedia(m.avatar);
                  const isPersona = m.member_type === "persona";
                  return (
                    <li key={m.id} className="flex items-center gap-3 border-b border-line px-3.5 py-2.5 last:border-b-0">
                      <span className={`flex size-8 flex-none items-center justify-center overflow-hidden rounded-full text-[11px] font-bold text-white ${isPersona ? "bg-accent" : "bg-gradient-to-br from-stone-500 to-stone-700"}`}>
                        {avatar ? (
                          // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media
                          <img src={avatar} alt="" className="size-full object-cover" />
                        ) : isPersona ? <Bot size={14} /> : (m.name || "?")[0]?.toUpperCase()}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-1.5 truncate text-[13.5px] font-semibold">
                          {isPersona ? `@${m.name}` : m.name}
                          {isPersona && <span className="rounded-full border border-accent/30 bg-accent/10 px-1.5 text-[10px] font-semibold text-accent">persona</span>}
                        </p>
                        {m.email && <p className="truncate text-[12px] text-ink2">{m.email}</p>}
                      </div>
                      {/* Detachable when managing: humans (non-owner) and personas
                          that are REAL project members. Synthetic persona rows
                          (id "persona:…", no ProjectMember row) carry the persona
                          id, not the shadow user id, so they can't be detached. */}
                      {canManage && m.role !== "owner" && !m.id.startsWith("persona:") && (
                        <button
                          aria-label={`${isPersona ? "Detach" : "Remove"} ${isPersona ? "@" : ""}${m.name} from ${projectName}`}
                          title={isPersona ? "Detach from project" : "Remove from project"}
                          disabled={busy} onClick={() => setRemoving(m)}
                          className="flex size-8 flex-none items-center justify-center rounded-lg text-ink2 hover:bg-crit/10 hover:text-crit disabled:opacity-40">
                          <Trash2 size={14} strokeWidth={2} />
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Add */}
          {canManage && (
          <section>
            <div className="mb-2 flex rounded-lg border border-line bg-surface2/70 p-0.5">
              {(["people", "personas"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`flex-1 rounded-md px-3 py-1 text-[12.5px] font-medium transition-colors ${tab === t ? "bg-surface text-ink shadow-sm" : "text-ink2 hover:text-ink"}`}>
                  {t === "people" ? "Add teammate" : "Add persona"}
                </button>
              ))}
            </div>

            {tab === "people" ? (
              (availUsers.data ?? []).length === 0 ? (
                <EmptyState icon={<UserPlus strokeWidth={1.8} />} title="No one left to add" hint="Everyone on the server is already on this project. Invite new people from Members." />
              ) : (
                <ul className="overflow-hidden rounded-xl border border-line bg-surface">
                  {(availUsers.data ?? []).map((u) => (
                    <li key={u.user_id} className="flex items-center gap-3 border-b border-line px-3.5 py-2.5 last:border-b-0">
                      <span className="flex size-8 flex-none items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-stone-500 to-stone-700 text-[11px] font-bold text-white">
                        {(u.name || u.email)[0]?.toUpperCase()}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13.5px] font-semibold">{u.name || u.email}</p>
                        {u.email && u.name && <p className="truncate text-[12px] text-ink2">{u.email}</p>}
                      </div>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => add.mutate(u.user_id)}>
                        <Plus size={14} strokeWidth={2} /> Add
                      </Button>
                    </li>
                  ))}
                </ul>
              )
            ) : (availPersonas.data ?? []).length === 0 ? (
              <EmptyState icon={<Bot strokeWidth={1.8} />} title="No personas to add" hint="Create a persona in Intelligence, then add it here to @mention it in this project." />
            ) : (
              <ul className="overflow-hidden rounded-xl border border-line bg-surface">
                {(availPersonas.data ?? []).map((p) => (
                  <li key={p.persona_id} className="flex items-center gap-3 border-b border-line px-3.5 py-2.5 last:border-b-0">
                    <span className="flex size-8 flex-none items-center justify-center overflow-hidden rounded-full bg-accent text-[11px] font-bold text-white">
                      <Bot size={14} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13.5px] font-semibold">@{p.name}</p>
                      {personaDetail(p.persona_id) && <p className="truncate text-[12px] text-ink2">{personaDetail(p.persona_id)}</p>}
                    </div>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => add.mutate(p.user_id)}>
                      <Plus size={14} strokeWidth={2} /> Add
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          )}
        </div>
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => { if (removing) remove.mutate(removing.user_id); setRemoving(null); }}
        title={removing?.member_type === "persona" ? "Detach this persona?" : "Remove from this project?"}
        body={removing?.member_type === "persona"
          ? <p><b className="text-ink">@{removing?.name}</b> will be detached from <b className="text-ink">{projectName}</b> — it won&apos;t be mentionable here. The persona itself stays, and you can add it back anytime.</p>
          : <p><b className="text-ink">{removing?.name}</b> loses access to <b className="text-ink">{projectName}</b>. They stay on the server and can be added back anytime.</p>}
        confirmLabel={removing?.member_type === "persona" ? "Detach" : "Remove"}
        loading={remove.isPending}
      />
    </>
  );
}
