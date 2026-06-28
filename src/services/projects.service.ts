import { apiJson } from "./api.client";
import type { Project } from "@/types";

export async function listProjects(companyId?: string): Promise<Project[]> {
  const qs = companyId ? `?company=${encodeURIComponent(companyId)}` : "";
  return apiJson<Project[]>(`/api/v1/projects/${qs}`);
}

export async function createProject(input: Partial<Project>): Promise<Project> {
  return apiJson<Project>("/api/v1/projects/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
