import type { Project } from "@/types";

// TODO: implement API calls for projects
export function listProjects(): Promise<Project[]> {
  throw new Error("Not implemented");
}

export function getProject(id: string): Promise<Project> {
  void id;
  throw new Error("Not implemented");
}

export function createProject(input: Partial<Project>): Promise<Project> {
  void input;
  throw new Error("Not implemented");
}

export function updateProject(id: string, input: Partial<Project>): Promise<Project> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteProject(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
