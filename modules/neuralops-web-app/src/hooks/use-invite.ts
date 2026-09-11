"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { inviteMember } from "@/lib/api/members";
import { notifyInvite } from "@/lib/invite-toast";
import { validateEmail } from "@/lib/validation";
import { useFormErrors } from "@/hooks/use-form-errors";
import { useConnectionStore } from "@/stores/connection.store";

export const DEFAULT_INVITE_ROLE = "member";

// One invite state machine for every surface that sends one (the members page,
// the members dialog). The host renders the fields through InviteFields and
// places its own buttons — a hook rather than a form component because the
// page's submit button sits in a dialog footer, outside the <form>.
export function useInvite({ onDone }: { onDone?: () => void } = {}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(DEFAULT_INVITE_ROLE);
  // The server's answer lives in err; form gates the button and shows a
  // field's rule under it once visited.
  const [err, setErr] = useState<string | null>(null);
  const form = useFormErrors({ email: [email, validateEmail(email)] });

  const reset = () => {
    setEmail("");
    setRole(DEFAULT_INVITE_ROLE);
    setErr(null);
    form.reset();
  };

  const invite = useMutation({
    mutationFn: () => inviteMember(email.trim(), role),
    onSuccess: (r) => {
      const { serverUrl, connection } = useConnectionStore.getState();
      notifyInvite(r, { serverUrl, appOrigin: window.location.origin, companyName: connection?.companyName });
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
    err, form, submit, reset,
    pending: invite.isPending,
    invalid: form.invalid,
  };
}

export type InviteState = ReturnType<typeof useInvite>;
