import { apiJson } from "./api.client";
import type { Persona } from "@/types";

export async function listPersonas(): Promise<Persona[]> {
  return apiJson<Persona[]>("/api/v1/personas/");
}

export async function createPersona(input: Partial<Persona>): Promise<Persona> {
  return apiJson<Persona>("/api/v1/personas/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
