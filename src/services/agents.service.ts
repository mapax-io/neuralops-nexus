import { apiJson } from "./api.client";
import type { Agent } from "@/types";

export async function listAgents(): Promise<Agent[]> {
  return apiJson<Agent[]>("/api/v1/agents/");
}

export async function getAgent(id: string): Promise<Agent> {
  return apiJson<Agent>(`/api/v1/agents/${id}/`);
}

export async function createAgent(input: Partial<Agent>): Promise<Agent> {
  return apiJson<Agent>("/api/v1/agents/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
