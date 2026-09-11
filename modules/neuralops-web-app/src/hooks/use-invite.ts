"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { inviteMember } from "@/lib/api/members";
import type { Project, Topic } from "@/lib/api/workspace";
import { fromGrants, pruneGrants, toGrants, type ProjectShape, type Selection } from "@/lib/invite-grants";
import { notifyInvite } from "@/lib/invite-toast";
import { validateEmail } from "@/lib/validation";
import { useFormErrors } from "@/hooks/use-form-errors";
import { useConnectionStore } from "@/stores/connection.store";

const DEFAULT_INVITE_ROLE = "member";

// One invite state machine for every surface that sends one (the members page,
// the members dialog). The host renders the fields through InviteFields and
// places its own buttons — a hook rather than a form component because the
// page's submit button sits in a dialog footer, outside the <form>.
export function useInvite({ onDone }: { onDone?: () => void } = {}) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(DEFAULT_INVITE_ROLE);
  // Which projects/topics they get the role in. Empty = the whole server,
  // the plain invite that always went out. With a selection the server puts
  // the role on those objects only — nothing company-wide.
  const [selection, setSelection] = useState<Selection>({});
  // The server's answer lives in err; form gates the button and shows a
  // field's rule under it once visited.
  const [err, setErr] = useState<string | null>(null);
  const form = useFormErrors({ email: [email, validateEmail(email)] });

  const reset = () => {
    setEmail("");
    setRole(DEFAULT_INVITE_ROLE);
    setSelection({});
    setErr(null);
    form.reset();
  };

  const invite = useMutation({
    mutationFn: async () => {
      const wanted = toGrants(selection);
      const requested = pruneGrants(wanted, knownProjects(qc));
      if (JSON.stringify(requested) !== JSON.stringify(wanted)) {
        // Something picked is gone (archived while the form was open). Never
        // send less or more than what is on screen: put the picks back in
        // step with the server, refresh the tree, and let the inviter look.
        setSelection(fromGrants(requested));
        void qc.invalidateQueries({ queryKey: ["projects"] });
        throw new Error("Some of what you picked is no longer on this server. The list has been refreshed — check it and send again.");
      }
      const r = await inviteMember(email.trim(), role, requested);
      return { ...r, requested };
    },
    onSuccess: (r) => {
      const { serverUrl, connection } = useConnectionStore.getState();
      notifyInvite(r, { serverUrl, appOrigin: window.location.origin, companyName: connection?.companyName });
      if (r.requested.length > 0 && !r.grants) {
        // A server from before grants existed ignores the field and hands out
        // server-wide access. That must never pass as done.
        toast.error("This server is out of date: they got server-wide access, not the projects you picked. Update the server, then check their access.", { duration: 15_000 });
      }
      // An open roster for a project they were added to should show them now.
      for (const g of r.grants ?? []) void qc.invalidateQueries({ queryKey: ["team", serverUrl, g.project_id] });
      reset();
      onDone?.();
    },
    onError: (e) => setErr(e.message),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (form.invalid) return form.touchAll();
    invite.mutate();
  };

  return {
    email, setEmail,
    role, setRole,
    selection, setSelection,
    scoped: Object.keys(selection).length > 0,
    err, form, submit, reset,
    pending: invite.isPending,
    invalid: form.invalid,
  };
}

export type InviteState = ReturnType<typeof useInvite>;

// What the app currently knows about projects and their topics, from the
// same cache the tree reads. A selected project's topics stay observed by the
// tree, so they are here whenever a pick could have been narrowed.
function knownProjects(qc: ReturnType<typeof useQueryClient>): ProjectShape[] {
  const { serverUrl } = useConnectionStore.getState();
  const projects = qc.getQueryData<Project[]>(["projects", serverUrl]) ?? [];
  return projects.map((p) => ({
    id: p.id,
    name: p.name,
    channels: p.channels.map((c) => ({
      id: c.id,
      name: c.name,
      topics: (qc.getQueryData<Topic[]>(["topics", serverUrl, p.id, c.id]) ?? []).map((t) => ({ id: t.id, title: t.title })),
    })),
  }));
}
