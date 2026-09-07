"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { FieldError, Input, Label } from "@/components/ui/field";
import { supabase } from "@/lib/supabase";

// The reset link from the email carries a recovery session in the URL; the
// identity SDK picks it up on load. Without one, updateUser can only fail —
// so the form waits for the session and says what to do when there is none.
export function ResetPasswordForm() {
  const router = useRouter();
  const [session, setSession] = useState<"checking" | "present" | "missing">("checking");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let alive = true;
    supabase()
      .auth.getSession()
      .then(({ data }) => alive && setSession(data.session ? "present" : "missing"))
      .catch(() => alive && setSession("missing"));
    return () => {
      alive = false;
    };
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Use at least 8 characters.");
    if (password !== confirm) return setError("Passwords don't match.");
    setPending(true);
    const { error: err } = await supabase().auth.updateUser({ password });
    setPending(false);
    if (err) {
      return setError(/session/i.test(err.message) ? "This reset link has expired or was already used — request a new one from the sign-in page." : err.message);
    }
    router.push("/servers");
  };

  if (session === "checking") return <p className="text-[13px] text-ink2" aria-busy>Checking your reset link…</p>;
  if (session === "missing") {
    return (
      <div role="alert" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2.5 text-[13px] text-ink">
        This page needs the link from your reset email — open it from there, or{" "}
        <Link href="/login" className="font-semibold underline underline-offset-2">request a new link</Link> from the sign-in page.
      </div>
    );
  }

  return (
    // method=post: an un-hydrated native submit keeps the password out of the URL.
    <form onSubmit={submit} method="post" noValidate className="flex flex-col gap-4">
      <div>
        <Label htmlFor="pw" required>New password</Label>
        <Input id="pw" type="password" required autoFocus autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <div>
        <Label htmlFor="pw2" required>Confirm password</Label>
        <Input id="pw2" type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </div>
      <FieldError>{error}</FieldError>
      <Button type="submit" variant="primary" size="lg" loading={pending}>Update password</Button>
    </form>
  );
}
