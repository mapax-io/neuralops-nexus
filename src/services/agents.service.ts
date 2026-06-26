import type { Agent } from "@/types";

// TODO: implement API calls for agents
export function listAgents(): Promise<Agent[]> {
  throw new Error("Not implemented");
}

export function getAgent(id: string): Promise<Agent> {
  void id;
  throw new Error("Not implemented");
}

export function createAgent(input: Partial<Agent>): Promise<Agent> {
  void input;
  throw new Error("Not implemented");
}

export function updateAgent(id: string, input: Partial<Agent>): Promise<Agent> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteAgent(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
