"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { BadgeCheck, Search, ShieldCheck, Trash2, UserPlus, Users, X } from "lucide-react";
import { toast } from "sonner";
import { AboutDialog } from "@/components/shell/about-dialog";
import { CommandPalette } from "@/components/shell/command-palette";
import { TopBar } from "@/components/shell/top-bar";
import { SectionHeader } from "@/components/ui/section-header";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/surfaces";
import { FullPageLoader } from "@/components/ui/full-page-loader";
import { absolutizeMedia } from "@/lib/api/client";
import { removeMember, type Member } from "@/lib/api/members";
import { useMembers } from "@/hooks/use-workspace";
import { useConnectionStore } from "@/stores/connection.store";
import { useInvite } from "@/hooks/use-invite";
import { InviteFields } from "@/components/shell/invite-fields";
import { MemberAccessDialog } from "@/components/shell/member-access-dialog";
import { usePermissions } from "@/hooks/use-permissions";
import { PermissionsBanner } from "@/components/shell/permissions-banner";
import { companyScope } from "@/lib/permissions";


// The team, at its own URL — no ids in the address bar.
export default function MembersPage() {
  const router = useRouter();
  const { token, serverUrl, hydrated, connection, email: selfEmail } = useConnectionStore();
  const { data: members, isLoading, error, refetch } = useMembers();
  const [about, setAbout] = useState(false);
  const [query, setQuery] = useState("");
  const [inviting, setInviting] = useState(false);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [accessFor, setAccessFor] = useState<Member | null>(null);
  const { can, loading: permsLoading } = usePermissions();
  // Both are genuinely company-scoped, so this page keeps a company check —
  // just against the right rather than the role string.
  const canInvite = can("company.invite_member", companyScope());
  const canRemove = can("company.remove_member", companyScope());

  useEffect(() => {
    if (!hydrated) return;
    if (!token) router.replace("/login");
    else if (!serverUrl) router.replace("/servers");
  }, [hydrated, token, serverUrl, router]);

  const remove = useMutation({
    mutationFn: (userId: string) => removeMember(userId),
    onSuccess: (r) => {
      toast.success(r.message || "Member removed.");
      refetch();
    },
    onError: (e) => toast.error(e.message),
  });

  const q = query.trim().toLowerCase();
  const visible = useMemo(
    () => (members ?? []).filter((m) => !q || m.email.toLowerCase().includes(q)),
    [members, q],
  );
  const admins = members?.filter((m) => m.role === "owner" || m.role === "admin").length ?? 0;

  // Rights decide which controls exist, so hold rather than paint a
  // screen with every gated control resolved to hidden.
  if (!hydrated || !token || !serverUrl || permsLoading) {
    return (
      <FullPageLoader />
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <TopBar onAbout={() => setAbout(true)} />
      <PermissionsBanner />
      <main className="nx-ambient min-h-0 min-w-0 flex-1 overflow-y-auto p-4 lg:px-6 lg:py-5">
        <div className="mx-auto w-full max-w-[1680px]">
          <SectionHeader
            title="Members"
            blurb={`Everyone on ${connection?.companyName ?? "this server"} — roles decide what they can manage.`}
            actions={canInvite && (
              <Button size="sm" variant="primary" onClick={() => setInviting(true)}>
                <UserPlus size={14} strokeWidth={2} /> Invite teammate
              </Button>
            )}
          />

          <div className="mb-4 mt-4 grid grid-cols-3 gap-3">
            {[
              { label: "Members", value: members?.length ?? "—" },
              { label: "Admins & owner", value: members ? admins : "—" },
              { label: "Regular members", value: members ? members.length - admins : "—" },
            ].map((st) => (
              <div key={st.label} className="rounded-xl border border-line bg-surface px-4 py-3">
                <p className="font-display text-[20px] font-extrabold leading-none tabular-nums">{st.value}</p>
                <p className="mt-1.5 text-[11.5px] font-medium text-ink2">{st.label}</p>
              </div>
            ))}
          </div>

          {(members?.length ?? 0) >= 6 && (
            <div className="mb-3 flex items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-2">
              <Search size={15} strokeWidth={2} className="flex-none text-ink2" />
              <input
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Filter ${members?.length} members…`}
                aria-label="Filter members"
                className="w-full bg-transparent text-[13.5px] outline-none placeholder:text-ink2/60"
              />
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col gap-2.5" role="status" aria-label="Loading members">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16 w-2/3" />
            </div>
          )}
          {!!error && (
            <p className="text-[13.5px] text-crit">
              Couldn&apos;t load members. <Button size="sm" variant="link" onClick={() => refetch()}>Retry</Button>
            </p>
          )}
          {!isLoading && !error && visible.length === 0 && (
            <div className="flex min-h-[40vh] items-center justify-center">
              <EmptyState
                icon={<Users strokeWidth={1.8} />}
                title={q ? `No member matches “${query}”` : "No members yet"}
                hint={q ? "Try a different email fragment." : "Invite your first teammate to get started."}
                action={
                  q ? (
                    <Button size="sm" onClick={() => setQuery("")}>Clear filter</Button>
                  ) : canInvite ? (
                    <Button size="sm" variant="primary" onClick={() => setInviting(true)}>
                      <UserPlus size={14} strokeWidth={2} /> Invite teammate
                    </Button>
                  ) : undefined
                }
              />
            </div>
          )}

          {visible.length > 0 && (
            <ul className="overflow-hidden rounded-xl border border-line bg-surface">
              {visible.map((m) => {
                const name = m.email.split("@")[0];
                const avatar = absolutizeMedia(m.avatar);
                const isSelf = !!selfEmail && m.email.toLowerCase() === selfEmail.toLowerCase();
                const removable = canRemove && !isSelf && m.role !== "owner"; // server enforces the same
                // Same gate as inviting; the server refuses the owner and yourself.
                const editable = canInvite && !isSelf && m.role !== "owner";
                return (
                  <li key={m.user_id} className="group flex items-center gap-3.5 border-b border-line px-4 py-3 last:border-b-0">
                    <span className="flex size-10 flex-none items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-stone-500 to-stone-700 text-[13px] font-bold text-white">
                      {avatar ? (
                        // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
                        <img src={avatar} alt="" className="size-full object-cover" />
                      ) : (
                        name[0]?.toUpperCase()
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">
                        {name}
                        {isSelf && <span className="font-normal text-ink2">(you)</span>}
                        <span className="flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2 py-px text-[10.5px] font-semibold text-accent">
                          <BadgeCheck size={11} strokeWidth={2} /> {m.role}
                        </span>
                      </p>
                      <p className="mt-0.5 truncate text-[12.5px] text-ink2">
                        {m.email}
                        <span aria-hidden> · </span>
                        joined {new Date(m.joined_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}
                        {m.invited_by && <span> · invited by {m.invited_by.split("@")[0]}</span>}
                      </p>
                    </div>
                    {editable && (
                      <Button size="sm" onClick={() => setAccessFor(m)} aria-label={`Access for ${name}`} className="flex-none">
                        <ShieldCheck size={14} strokeWidth={2} /> Access
                      </Button>
                    )}
                    {removable && (
                      <button
                        aria-label={`Remove ${name} from this server`}
                        title="Remove from server"
                        onClick={() => setRemoving(m)}
                        className="flex size-8 flex-none items-center justify-center rounded-md text-ink2 hover:bg-crit/10 hover:text-crit opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <Trash2 size={15} strokeWidth={2} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>
      <InviteDialog open={inviting} onClose={() => setInviting(false)} onDone={() => refetch()} />
      <MemberAccessDialog member={accessFor} open={!!accessFor} onClose={() => setAccessFor(null)} onSaved={() => refetch()} />
      <ConfirmDialog
        open={!!removing}
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          if (removing) remove.mutate(removing.user_id);
          setRemoving(null);
        }}
        title="Remove this member?"
        body={
          <p>
            <b className="text-ink">{removing?.email}</b> loses access to this server and everything on it.
            They can be invited back later.
          </p>
        }
        confirmLabel="Remove member"
        loading={remove.isPending}
      />
      <AboutDialog open={about} onClose={() => setAbout(false)} />
      <CommandPalette onAbout={() => setAbout(true)} />
    </div>
  );
}

function InviteDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  // A sent invite closes the dialog; the hook has already reset the fields.
  const inv = useInvite({ onDone: () => { onClose(); onDone(); } });
  // Closing forgets the half-typed invite and its error — reopening starts clean.
  const close = () => {
    inv.reset();
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Invite a teammate"
      description="They sign in with this email and land on the server as a member the moment they connect."
      icon={<UserPlus size={17} strokeWidth={2} />}
      tone="accent"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}><X size={14} strokeWidth={2} /> Cancel</Button>
          <Button type="submit" form="mi-form" size="sm" variant="primary" disabled={inv.invalid} loading={inv.pending}><UserPlus size={14} strokeWidth={2} /> Invite</Button>
        </div>
      }
    >
      <form id="mi-form" onSubmit={inv.submit} noValidate className="flex flex-col gap-4">
        <InviteFields inv={inv} idPrefix="mi" />
      </form>
    </Dialog>
  );
}
