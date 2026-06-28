import { apiJson } from "./api.client";
import type { Notification } from "@/types";

export async function listNotifications(): Promise<Notification[]> {
  return apiJson<Notification[]>("/api/v1/notifications/");
}

export async function markRead(id: string): Promise<void> {
  await apiJson<void>(`/api/v1/notifications/${id}/read/`, { method: "POST" });
}
