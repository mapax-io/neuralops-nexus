"use client";

import { FieldError, Input, Label } from "@/components/ui/field";
import { InviteAccessTree } from "@/components/shell/invite-access-tree";
import type { InviteState } from "@/hooks/use-invite";

const selectClass = "h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]";

// The role a person holds on the server, with the server's rule said plainly:
// with picks it applies only there, never company-wide. Shared by the invite
// form and the member access editor so the two can never disagree.
export function CompanyRoleSelect({ id, value, onChange, scoped }: {
  id: string;
  value: string;
  onChange: (role: string) => void;
  // Whether projects/topics are picked alongside it.
  scoped: boolean;
}) {
  return (
    <div>
      <Label htmlFor={id}>Company role</Label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={selectClass}>
        <option value="member">Member — works in projects</option>
        <option value="admin">Admin — manages projects, models, people</option>
        <option value="viewer">Viewer — read-only</option>
      </select>
      <p className="mt-1.5 text-[12px] text-ink2">
        {scoped
          ? "Applies only in the projects and topics picked below — nothing else on the server."
          : "Applies across the whole server. Pick projects below to limit it to them."}
      </p>
    </div>
  );
}

// The invite form's fields, bound to useInvite(). The host owns the <form>
// and the buttons; idPrefix keeps ids unique when two hosts share a page.
export function InviteFields({ inv, idPrefix }: { inv: InviteState; idPrefix: string }) {
  return (
    <>
      <div>
        <Label htmlFor={`${idPrefix}-email`} required>Email</Label>
        <Input
          id={`${idPrefix}-email`}
          type="email"
          required
          autoFocus
          placeholder="teammate@company.com"
          value={inv.email}
          aria-invalid={!!inv.form.error("email") || !!inv.err}
          onChange={(e) => inv.setEmail(e.target.value)}
          onBlur={() => inv.form.touch("email")}
        />
        <FieldError>{inv.form.error("email")}</FieldError>
      </div>
      <CompanyRoleSelect id={`${idPrefix}-role`} value={inv.role} onChange={inv.setRole} scoped={inv.scoped} />
      <fieldset>
        <legend className="mb-1.5 block text-[13px] font-medium text-ink2">
          Projects and topics <span className="font-normal">(optional)</span>
        </legend>
        <InviteAccessTree selection={inv.selection} onChange={inv.setSelection} idPrefix={idPrefix} />
      </fieldset>
      <FieldError>{inv.err}</FieldError>
    </>
  );
}
