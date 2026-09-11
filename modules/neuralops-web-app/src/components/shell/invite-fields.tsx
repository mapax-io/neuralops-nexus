"use client";

import { FieldError, Input, Label } from "@/components/ui/field";
import type { InviteState } from "@/hooks/use-invite";

const selectClass = "h-10 w-full rounded-[10px] border border-line bg-surface px-3 text-[14px] outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-soft)]";

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
      <div>
        <Label htmlFor={`${idPrefix}-role`}>Role</Label>
        <select id={`${idPrefix}-role`} value={inv.role} onChange={(e) => inv.setRole(e.target.value)} className={selectClass}>
          <option value="member">Member — works in projects</option>
          <option value="admin">Admin — manages projects, models, people</option>
          <option value="viewer">Viewer — read-only</option>
        </select>
      </div>
      <FieldError>{inv.err}</FieldError>
    </>
  );
}
