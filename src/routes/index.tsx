import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import { useAuthStore } from "@/store/auth.store";
import { Sparkles } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Sign in — NeuralOps" },
      { name: "description", content: "Sign in to your NeuralOps workspace." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const supabaseToken = useAuthStore((s) => s.supabaseToken);
  const serverUrl = useAuthStore((s) => s.serverUrl);

  useEffect(() => {
    if (supabaseToken && serverUrl) {
      navigate({ to: "/app", replace: true });
    } else if (supabaseToken) {
      navigate({ to: "/servers", replace: true });
    }
  }, [supabaseToken, serverUrl, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-subtle px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">
            Welcome to NeuralOps
          </h1>
          <p className="mt-1 text-sm text-foreground-muted">
            Sign in to access your AI workspace
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-6">
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
