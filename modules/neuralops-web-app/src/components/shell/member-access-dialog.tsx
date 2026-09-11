"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/surfaces";
import { CompanyRoleSelect } from "@/components/shell/invite-fields";
import { InviteAccessTree } from "@/components/shell/invite-access-tree";
import { useDelayedLoading } from "@/hooks/use-delayed-loading";
import { getMemberAccess, setMemberAccess, type Member } from "@/lib/api/members";
import { fromGrants, toGrants, type Selection } from "@/lib/invite-grants";
import { useConnectionStore } from "@/stores/connection.store";

interface Draft { role: string; selection: Selection }

// View and change what a member holds: the same role select and tree the
// invite uses, loaded with what the server says they have now. Saving is a
// full replace under the invite's rule -- nothing picked is the whole server.
export function MemberAccessDialog({ member, open, onClose, onSaved }: {
  member: Member | null;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const serverUrl = useConnectionStore((s) => s.serverUrl);
  const token = useConnectionStore((s) => s.token);
  const key = ["member-access", serverUrl, member?.user_id];
  const access = useQuery({
    queryKey: key,
    queryFn: () => getMemberAccess(member!.user_id),
    enabled: open && !!member && !!serverUrl && !!token,
  });
  const showLoader = useDelayedLoading(access.isPending && access.fetchStatus !== "idle");

  // Derived, not synced: the server's answer is the base; edits sit on top and
  // are dropped on close. No effect copies one into the other.
  const base: Draft | null = access.data
    ? { role: access.data.role, selection: access.data.server_wide ? {} : fromGrants(access.data.grants) }
    : null;
  const [edits, setEdits] = useState<Draft | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const draft = edits ?? base;
  const dirty = !!edits && !!base && (
    edits.role !== base.role || JSON.stringify(toGrants(edits.selection)) !== JSON.stringify(toGrants(base.selection))
  );

  const close = () => {
    setEdits(null);
    setErr(null);
    onClose();
  };
  const name = member?.email.split("@")[0] ?? "";
  const save = useMutation({
    mutationFn: () => setMemberAccess(member!.user_id, { role: draft!.role, grants: toGrants(draft!.selection) }),
    onSuccess: (r) => {
      qc.setQueryData(key, r);
      toast.success(`${name}'s access updated.`);
      onSaved();
      close();
    },
    onError: (e) => setErr(e.message),
  });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (dirty) save.mutate();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={`Access for ${name}`}
      description="What they can reach on this server. Pick nothing for the whole server; pick projects or topics to limit them to those."
      icon={<ShieldCheck size={17} strokeWidth={2} />}
      tone="accent"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={close}><X size={14} strokeWidth={2} /> Cancel</Button>
          <Button type="submit" form="ma-form" size="sm" variant="primary" disabled={!dirty} loading={save.isPending}>
            <Save size={14} strokeWidth={2} /> Save
          </Button>
        </div>
      }
    >
      {access.isPending ? (
        showLoader ? (
          <div className="flex flex-col gap-3" role="status" aria-label="Loading access">
            <Skeleton className="h-10" />
            <Skeleton className="h-24" />
          </div>
        ) : null
      ) : access.error ? (
        <FieldError>
          Couldn&apos;t load their access.{" "}
          <button type="button" onClick={() => access.refetch()} className="underline hover:text-ink">Retry</button>
        </FieldError>
      ) : draft ? (
        <form id="ma-form" onSubmit={submit} noValidate className="flex flex-col gap-4">
          <CompanyRoleSelect
            id="ma-role"
            value={draft.role}
            onChange={(role) => setEdits({ ...draft, role })}
            scoped={Object.keys(draft.selection).length > 0}
          />
          <fieldset>
            <legend className="mb-1.5 block text-[13px] font-medium text-ink2">Projects and topics</legend>
            <InviteAccessTree selection={draft.selection} onChange={(selection) => setEdits({ ...draft, selection })} idPrefix="ma" />
          </fieldset>
          <FieldError>{err}</FieldError>
        </form>
      ) : null}
    </Dialog>
  );
}
