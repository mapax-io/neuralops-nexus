"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { BadgeCheck, UserPlus, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/surfaces";
import { absolutizeMedia } from "@/lib/api/client";
import { inviteMember } from "@/lib/api/members";
import { useMembers } from "@/hooks/use-workspace";
import { useQuery } from "@tanstack/react-query";
import { listTeam } from "@/lib/api/team";
import { listPersonas } from "@/lib/api/intelligence";
import { useConnectionStore } from "@/stores/connection.store";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Slack-style member list for the chat header's avatar stack: everyone on
// this server, plus invites for those allowed to send them.
export function MembersDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: members, isLoading, error, refetch } = useMembers();
  const role = useConnectionStore((s) => s.connection?.role);
  const selfEmail = useConnectionStore((s) => s.email);
  const canInvite = role === "owner" || role === "admin";
  const [inviting, setInviting] = useState(false);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [err, setErr] = useState<string | null>(null);

  const router = useRouter();
  const invite = useMutation({
    mutationFn: () => inviteMember(email.trim(), inviteRole),
    onSuccess: (r) => {
      toast.success(r.message || `Invitation sent to ${r.email}.`);
      setEmail("");
      setInviting(false);
      refetch();
    },
    onError: (e) => setErr(e.message),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!EMAIL_RE.test(email.trim())) return setErr("Enter a valid email address.");
    invite.mutate();
  };

  // Closing forgets the half-typed invite and its error — reopening starts clean.
  const close = () => {
    setInviting(false);
    setEmail("");
    setErr(null);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Members"
      description="Everyone on this server. Invited people join with the email they sign in with."
      icon={<Users size={17} strokeWidth={2} />}
      footer={
        <div className="flex items-center justify-between gap-2">
          {canInvite && !inviting ? (
            <Button size="sm" onClick={() => setInviting(true)}>
              <UserPlus size={14} strokeWidth={2} /> Invite a teammate
            </Button>
          ) : (
            <span />
          )}
          <Button size="sm" variant="ghost" onClick={() => { close(); router.push("/members"); }}>
            View all members →
          </Button>
        </div>
      }
    >
      {isLoading && <div className="flex flex-col gap-2"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
      {!!error && (
        <p className="py-3 text-[13px] text-crit">
          Couldn&apos;t load members.{" "}
          <button className="underline hover:text-ink" onClick={() => refetch()}>Retry</button>
        </p>
      )}
      <ul>
        {members?.map((m) => {
          const name = m.email.split("@")[0];
          const avatar = absolutizeMedia(m.avatar);
          const isSelf = !!selfEmail && m.email.toLowerCase() === selfEmail.toLowerCase();
          return (
            <li key={m.user_id} className="flex items-center gap-3 border-b border-line py-2.5 last:border-b-0">
              <span className="flex size-8 flex-none items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-stone-500 to-stone-700 text-[12px] font-bold text-white">
                {avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
                  <img src={avatar} alt="" className="size-full object-cover" />
                ) : (
                  name[0]?.toUpperCase()
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-semibold">
                  {name}
                  {isSelf && <span className="font-normal text-ink2"> (you)</span>}
                </p>
                <p className="truncate text-[12px] text-ink2">{m.email}</p>
              </div>
              <span className="flex flex-none items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10.5px] font-semibold text-accent">
                <BadgeCheck size={11} strokeWidth={2} /> {m.role}
              </span>
            </li>
          );
        })}
      </ul>
      {canInvite && inviting && (
        <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-3 rounded-xl border border-line bg-surface2/50 p-3.5">
          <div>
            <Label htmlFor="inv-email" required>Email</Label>
            <Input id="inv-email" type="email" required autoFocus placeholder="teammate@company.com" value={email} aria-invalid={!!err} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="inv-role">Role</Label>
            <select
              id="inv-role"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]"
            >
              <option value="member">Member — works in projects</option>
              <option value="admin">Admin — manages projects, models, people</option>
              <option value="viewer">Viewer — read-only</option>
            </select>
          </div>
          <FieldError>{err}</FieldError>
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" onClick={() => setInviting(false)}>Cancel</Button>
            <Button type="submit" size="sm" variant="primary" loading={invite.isPending}>Send invite</Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

// The header affordance: overlapping avatars + member count, Slack-style.
export function MemberStack({ onClick, pid }: { onClick: () => void; pid?: string }) {
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  // In a project context show the TEAM (humans + personas); otherwise the
  // server's human members.
  const gate = !!serverUrl && !!token && !!pid;
  const team = useQuery({ queryKey: ["team", serverUrl, pid], queryFn: () => listTeam(pid!), enabled: gate });
  const personas = useQuery({ queryKey: ["personas", serverUrl, pid], queryFn: () => listPersonas(pid!), enabled: gate });
  const server = useMembers();
  // Project context: humans on the team + personas usable here. Otherwise the
  // server's human members.
  const members = pid
    ? [
        ...(team.data ?? []).filter((m) => m.member_type !== "persona"),
        ...(team.data ?? []).filter((m) => m.member_type === "persona"),
        ...(personas.data ?? [])
          .filter((pp) => !(team.data ?? []).some((m) => m.member_type === "persona" && m.user_id === pp.id))
          .map((pp) => ({ user_id: pp.id, email: "", name: pp.name, avatar: pp.avatar ?? null })),
      ]
    : server.data;
  if (!members?.length) return null;
  const shown = members.slice(0, 3);
  return (
    <button
      aria-label={`${members.length} members — view all`}
      title={`${members.length} ${members.length === 1 ? "member" : "members"}`}
      onClick={onClick}
      className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-1.5 py-1 transition-colors hover:border-accent"
    >
      <span className="flex -space-x-1.5">
        {shown.map((m) => {
          const avatar = absolutizeMedia(m.avatar);
          return (
            <span key={m.user_id} className="flex size-5.5 items-center justify-center overflow-hidden rounded-md border border-surface bg-gradient-to-br from-stone-500 to-stone-700 text-[9px] font-bold text-white">
              {avatar ? (
                // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
                <img src={avatar} alt="" className="size-full object-cover" />
              ) : (
                (m.email || ("name" in m ? (m as { name: string }).name : "?"))[0]?.toUpperCase()
              )}
            </span>
          );
        })}
      </span>
      <span className="pr-0.5 text-[12px] font-semibold text-ink2">{members.length}</span>
    </button>
  );
}
