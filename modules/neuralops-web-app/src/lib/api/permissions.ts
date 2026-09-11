import { apiJson } from "./client";
import type { Permissions } from "@/lib/permissions";

// The user's effective rights, already resolved for reach by the server.
// Servers older than this endpoint answer 404 — usePermissions() treats that
// as "unavailable" and falls back, never as "holds nothing".
export const getMyPermissions = () => apiJson<Permissions>(`/api/v1/me/permissions/`);
