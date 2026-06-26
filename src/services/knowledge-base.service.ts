import type { KnowledgeBaseItem } from "@/types";

// TODO: implement API calls for knowledge-base
export function listKnowledgeBaseItems(): Promise<KnowledgeBaseItem[]> {
  throw new Error("Not implemented");
}

export function getKnowledgeBaseItem(id: string): Promise<KnowledgeBaseItem> {
  void id;
  throw new Error("Not implemented");
}

export function createKnowledgeBaseItem(input: Partial<KnowledgeBaseItem>): Promise<KnowledgeBaseItem> {
  void input;
  throw new Error("Not implemented");
}

export function updateKnowledgeBaseItem(id: string, input: Partial<KnowledgeBaseItem>): Promise<KnowledgeBaseItem> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteKnowledgeBaseItem(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
