import type { Persona } from "@/types";

// TODO: implement API calls for personas
export function listPersonas(): Promise<Persona[]> {
  throw new Error("Not implemented");
}

export function getPersona(id: string): Promise<Persona> {
  void id;
  throw new Error("Not implemented");
}

export function createPersona(input: Partial<Persona>): Promise<Persona> {
  void input;
  throw new Error("Not implemented");
}

export function updatePersona(id: string, input: Partial<Persona>): Promise<Persona> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deletePersona(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
