"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { FieldError, Input, Label } from "@/components/ui/field";

// Sign-in never length-checks — existing accounts may predate any policy,
// and the server is the judge. Length rules apply only where a password is
// being SET (sign-up here, reset page, profile dialog) — all agree on 8.
const signInSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
const signUpSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Use at least 8 characters."),
});
const emailOnlySchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string(),
});
type FormValues = z.infer<typeof signUpSchema>;

type Mode = "signin" | "signup" | "forgot";

export function LoginForm() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(mode === "forgot" ? emailOnlySchema : mode === "signup" ? signUpSchema : signInSchema),
    defaultValues: { email: "", password: "" },
  });

  const submit = form.handleSubmit(async ({ email, password }) => {
    setServerError(null);
    setNotice(null);
    setPending(true);
    try {
      const sb = supabase();
      if (mode === "forgot") {
        const { error } = await sb.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
        if (error) throw error;
        setNotice("Check your email for a reset link.");
        return;
      }
      const { data, error } =
        mode === "signin"
          ? await sb.auth.signInWithPassword({ email, password })
          : await sb.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } });
      if (error) throw error;
      if (!data.session) {
        setNotice("Check your email to confirm your account, then sign in.");
        return;
      }
      router.push("/servers");
    } catch (e) {
      setServerError(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setPending(false);
    }
  });

  const [githubPending, setGithubPending] = useState(false);
  const github = async () => {
    setServerError(null);
    setGithubPending(true); // stays pending through the redirect — double-clicks fire the OAuth flow twice
    const { error } = await supabase().auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: `${window.location.origin}/servers` },
    });
    if (error) {
      // The most common failure is config, not the user — say so plainly.
      setServerError(
        /not enabled|unsupported provider/i.test(error.message)
          ? "GitHub sign-in isn't switched on for this workspace yet — ask the owner to enable the GitHub provider in the identity settings. Email sign-in works meanwhile."
          : error.message,
      );
      setGithubPending(false);
    }
  };

  // method=post so an un-hydrated native submit puts credentials in the request
  // body, never the URL/query string. Inert once JS handles submit.
  return (
    <form onSubmit={submit} method="post" noValidate className="flex flex-col gap-4">
      <div>
        <Label htmlFor="email" required>Email</Label>
        <Input id="email" type="email" required autoFocus autoComplete="email" placeholder="you@company.com" {...form.register("email")} />
        <FieldError>{form.formState.errors.email?.message}</FieldError>
      </div>
      {mode !== "forgot" && (
        <div>
          <Label htmlFor="password" required>Password</Label>
          <Input id="password" type="password" required autoComplete={mode === "signin" ? "current-password" : "new-password"} {...form.register("password")} />
          <FieldError>{form.formState.errors.password?.message}</FieldError>
        </div>
      )}
      {serverError && <p role="alert" className="rounded-lg border border-crit/30 bg-crit/10 px-3 py-2 text-[13px] text-crit">{serverError}</p>}
      {notice && <p role="status" className="rounded-lg border border-ok/30 bg-ok/10 px-3 py-2 text-[13px] text-ok">{notice}</p>}
      <Button type="submit" variant="primary" size="lg" loading={pending}>
        {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
      </Button>
      {mode !== "forgot" && (
        <Button type="button" onClick={github} loading={githubPending}>Continue with GitHub</Button>
      )}
      <div className="flex justify-between text-[13px] text-ink2">
        <button type="button" className="hover:text-ink" onClick={() => { form.clearErrors(); setNotice(null); setServerError(null); setMode(mode === "signin" ? "signup" : "signin"); }}>
          {mode === "signin" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
        {mode === "signin" && (
          <button type="button" className="hover:text-ink" onClick={() => { form.clearErrors(); setNotice(null); setServerError(null); setMode("forgot"); }}>Forgot password?</button>
        )}
        {mode === "forgot" && (
          <button type="button" className="hover:text-ink" onClick={() => { form.clearErrors(); setNotice(null); setServerError(null); setMode("signin"); }}>Back to sign in</button>
        )}
      </div>
    </form>
  );
}
