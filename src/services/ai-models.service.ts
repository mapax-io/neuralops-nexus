import { apiJson } from "./api.client";
import type { AIModel } from "@/types";

export async function listAIModels(): Promise<AIModel[]> {
  return apiJson<AIModel[]>("/api/v1/ai-models/");
}
