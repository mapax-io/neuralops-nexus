"use client";

import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export default function ResetPasswordPage() {
  return (
    <AuthShell title="Set your password" subtitle="From a password reset or an invitation email.">
      <ResetPasswordForm />
    </AuthShell>
  );
}
