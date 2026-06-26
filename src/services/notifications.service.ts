import type { Notification } from "@/types";

// TODO: implement API calls for notifications
export function listNotifications(): Promise<Notification[]> {
  throw new Error("Not implemented");
}

export function getNotification(id: string): Promise<Notification> {
  void id;
  throw new Error("Not implemented");
}

export function createNotification(input: Partial<Notification>): Promise<Notification> {
  void input;
  throw new Error("Not implemented");
}

export function updateNotification(id: string, input: Partial<Notification>): Promise<Notification> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteNotification(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
