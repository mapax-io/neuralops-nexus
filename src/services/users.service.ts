import { apiJson } from "./api.client";
import type { User } from "@/types";

export async function listUsers(): Promise<User[]> {
  return apiJson<User[]>("/api/v1/users/");
}

export async function getCurrentUser(): Promise<User> {
  return apiJson<User>("/api/v1/users/me/");
}
