import type { User } from "@/types";

// TODO: implement API calls for users
export function listUsers(): Promise<User[]> {
  throw new Error("Not implemented");
}

export function getUser(id: string): Promise<User> {
  void id;
  throw new Error("Not implemented");
}

export function createUser(input: Partial<User>): Promise<User> {
  void input;
  throw new Error("Not implemented");
}

export function updateUser(id: string, input: Partial<User>): Promise<User> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteUser(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
