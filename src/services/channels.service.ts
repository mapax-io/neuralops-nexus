import type { Channel } from "@/types";

// TODO: implement API calls for channels
export function listChannels(): Promise<Channel[]> {
  throw new Error("Not implemented");
}

export function getChannel(id: string): Promise<Channel> {
  void id;
  throw new Error("Not implemented");
}

export function createChannel(input: Partial<Channel>): Promise<Channel> {
  void input;
  throw new Error("Not implemented");
}

export function updateChannel(id: string, input: Partial<Channel>): Promise<Channel> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteChannel(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
