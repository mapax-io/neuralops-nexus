"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Check, KeyRound, LogOut, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogSection } from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/field";
import { changeUsername, USERNAME_RE } from "@/lib/api/account";
import { absolutizeMedia } from "@/lib/api/client";
import { supabase } from "@/lib/supabase";
import { useMembers } from "@/hooks/use-workspace";
import { useConnectionStore } from "@/stores/connection.store";
import { useFormErrors } from "@/hooks/use-form-errors";

// Profile & account settings. Identity is split across two systems on
// purpose: password lives with Supabase (who you are), display name lives on
// the connected server (who you are THERE). Avatars are assigned server-side
// — there is no upload endpoint yet (docs/OPEN-ITEMS.md).
export function ProfileDialog({ open, onClose, onSignOut }: { open: boolean; onClose: () => void; onSignOut: () => void }) {
  const { email, connection } = useConnectionStore();
  const { data: members } = useMembers();
  const qc = useQueryClient();
  const self = members?.find((m) => m.user_id === connection?.nucleusUserId);
  const avatar = absolutizeMedia(self?.avatar ?? null);
  // The members API doesn't expose display_name (OPEN-ITEMS) — show the last
  // rename from this dialog, else the email-derived default the server uses.
  const [savedName, setSavedName] = useState<string | null>(null);
  const currentName = savedName ?? (self ? self.email.split("@")[0] : (email ?? "").split("@")[0]);

  const [name, setName] = useState("");
  const [nameErr, setNameErr] = useState<string | null>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [pwErr, setPwErr] = useState<string | null>(null);

  const validateName = (v: string) => {
    if (!v.trim()) return "Enter a name.";
    if (!USERNAME_RE.test(v.trim())) return "2–30 characters — letters, numbers and underscores only.";
    return null;
  };
  // Each form's rules derived live: its button gates on them, each field
  // shows its own once visited. nameErr / pwErr keep the server's answer.
  const nameForm = useFormErrors({ name: [name, validateName(name)] });
  const pwForm = useFormErrors({
    pw: [pw, pw.length < 8 ? "Use at least 8 characters." : null],
    pw2: [pw2, pw2 !== pw ? "The two passwords don't match." : null],
  });

  const rename = useMutation({
    mutationFn: () => changeUsername(name.trim(), ""),
    onSuccess: (out) => {
      toast.success(`You're now "${out.display_name}" on this server.`);
      setSavedName(out.display_name);
      setName("");
      setNameErr(null);
      nameForm.reset();
      qc.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (e) => setNameErr(e.message),
  });

  const changePw = useMutation({
    mutationFn: async () => {
      const { error } = await supabase().auth.updateUser({ password: pw });
      if (error) throw new Error(error.message);
    },
    onSuccess: () => {
      toast.success("Password updated. Use it next time you sign in.");
      setPw("");
      setPw2("");
      setPwErr(null);
      pwForm.reset();
    },
    onError: (e) => setPwErr(e.message),
  });

  const submitName = (e: React.FormEvent) => {
    e.preventDefault();
    if (nameForm.invalid) return nameForm.touchAll();
    setNameErr(null);
    rename.mutate();
  };

  const submitPw = (e: React.FormEvent) => {
    e.preventDefault();
    if (pwForm.invalid) return pwForm.touchAll();
    setPwErr(null);
    changePw.mutate();
  };

  // A half-typed password must not survive the dialog — reopening shows a
  // clean form, never yesterday's masked-but-submittable input.
  const close = () => {
    setName("");
    setNameErr(null);
    setPw("");
    setPw2("");
    setPwErr(null);
    nameForm.reset();
    pwForm.reset();
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      size="lg"
      title="Your profile"
      description="Your password belongs to your NeuralOps account; your display name lives on this server."
      icon={<UserRound size={17} strokeWidth={2} />}
      tone="accent"
      footer={
        <div className="flex justify-end">
          <Button type="button" size="sm" variant="ghost" onClick={onSignOut}>
            <LogOut size={14} strokeWidth={2} /> Sign out
          </Button>
        </div>
      }
    >
      <div className="flex items-center gap-3.5 rounded-xl border border-line bg-surface2/60 p-3.5">
        <span className="flex size-12 flex-none items-center justify-center overflow-hidden rounded-full bg-accent text-[16px] font-bold text-accent-ink">
          {avatar ? (
            // eslint-disable-next-line @next/next/no-img-element -- runtime server-relative media, domain unknown at build
            <img src={avatar} alt="" className="size-full object-cover" />
          ) : (
            (currentName || "?")[0]?.toUpperCase()
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 truncate text-[14px] font-semibold">
            {currentName}
            {connection?.role && (
              <span className="flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-1.5 py-px text-[10px] font-semibold text-accent">
                <BadgeCheck size={11} strokeWidth={2} /> {connection.role}
              </span>
            )}
          </p>
          <p className="truncate text-[12.5px] text-ink2">{email}</p>
          <p className="mt-0.5 text-[11.5px] text-ink2/80">Photo is assigned by the server — custom uploads are coming.</p>
        </div>
      </div>

      <DialogSection title="Your name" hint="How teammates and personas see you on this server." className="mt-5">
      <form onSubmit={submitName} noValidate>
        <Label htmlFor="prof-name" required>Display name on {connection?.companyName ?? "this server"}</Label>
        <div className="flex gap-2">
          <Input
            id="prof-name"
            required
            autoFocus
            placeholder={currentName || "your_name"}
            value={name}
            aria-invalid={!!(nameForm.error("name") ?? nameErr)}
            onChange={(e) => { setName(e.target.value); setNameErr(null); }}
            onBlur={() => nameForm.touch("name")}
          />
          <Button type="submit" size="sm" variant="primary" loading={rename.isPending} disabled={nameForm.invalid} className="flex-none self-start"><Check size={14} strokeWidth={2} /> Save
          </Button>
        </div>
        {(nameForm.error("name") ?? nameErr) ? <FieldError>{nameForm.error("name") ?? nameErr}</FieldError> : <p className="mt-1.5 text-[12px] text-ink2">Teammates and personas will see this name. 2–30 characters, no spaces.</p>}
      </form>
      </DialogSection>

      <DialogSection title="Change password" hint="Belongs to your NeuralOps account, not to this server.">
      {/* method=post: an un-hydrated native submit keeps the password out of the URL. */}
      <form onSubmit={submitPw} method="post" noValidate>
        <div className="flex flex-col gap-3">
          <div>
            <Label htmlFor="prof-pw" required>New password</Label>
            <Input id="prof-pw" type="password" required autoComplete="new-password" value={pw} aria-invalid={!!pwForm.error("pw") || !!pwErr} onChange={(e) => { setPw(e.target.value); setPwErr(null); }} onBlur={() => pwForm.touch("pw")} />
            <FieldError>{pwForm.error("pw")}</FieldError>
          </div>
          <div>
            <Label htmlFor="prof-pw2" required>Confirm new password</Label>
            <Input id="prof-pw2" type="password" required autoComplete="new-password" value={pw2} aria-invalid={!!pwForm.error("pw2") || !!pwErr} onChange={(e) => { setPw2(e.target.value); setPwErr(null); }} onBlur={() => pwForm.touch("pw2")} />
            <FieldError>{pwForm.error("pw2")}</FieldError>
          </div>
          <FieldError>{pwErr}</FieldError>
          <div className="flex">
            <Button type="submit" size="sm" variant="primary" loading={changePw.isPending} disabled={pwForm.invalid}><KeyRound size={14} strokeWidth={2} /> Update password
            </Button>
          </div>
        </div>
      </form>
      </DialogSection>
    </Dialog>
  );
}
