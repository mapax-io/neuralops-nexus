import type { Topic } from "@/types";

// TODO: implement API calls for topics
export function listTopics(): Promise<Topic[]> {
  throw new Error("Not implemented");
}

export function getTopic(id: string): Promise<Topic> {
  void id;
  throw new Error("Not implemented");
}

export function createTopic(input: Partial<Topic>): Promise<Topic> {
  void input;
  throw new Error("Not implemented");
}

export function updateTopic(id: string, input: Partial<Topic>): Promise<Topic> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteTopic(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
