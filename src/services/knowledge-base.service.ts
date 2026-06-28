import { apiJson } from "./api.client";
import type { KnowledgeItem } from "@/types";

export async function listKnowledge(): Promise<KnowledgeItem[]> {
  return apiJson<KnowledgeItem[]>("/api/v1/knowledge/");
}

export async function createKnowledge(
  input: Partial<KnowledgeItem>,
): Promise<KnowledgeItem> {
  return apiJson<KnowledgeItem>("/api/v1/knowledge/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
