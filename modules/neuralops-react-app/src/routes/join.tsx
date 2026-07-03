/**
 * /join — no longer used.
 * Invites work by email pre-authorisation: the invited person signs up
 * and connects to the server address you share with them.
 * auth_verify handles the rest automatically.
 */
import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/join")({
  beforeLoad: () => {
    throw redirect({ to: "/", replace: true });
  },
  component: () => null,
});
