import type { Message } from "@/types";

// TODO: implement API calls for messages
export function listMessages(): Promise<Message[]> {
  throw new Error("Not implemented");
}

export function getMessage(id: string): Promise<Message> {
  void id;
  throw new Error("Not implemented");
}

export function createMessage(input: Partial<Message>): Promise<Message> {
  void input;
  throw new Error("Not implemented");
}

export function updateMessage(id: string, input: Partial<Message>): Promise<Message> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteMessage(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
