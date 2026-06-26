import type { AiModel } from "@/types";

// TODO: implement API calls for ai-models
export function listAiModels(): Promise<AiModel[]> {
  throw new Error("Not implemented");
}

export function getAiModel(id: string): Promise<AiModel> {
  void id;
  throw new Error("Not implemented");
}

export function createAiModel(input: Partial<AiModel>): Promise<AiModel> {
  void input;
  throw new Error("Not implemented");
}

export function updateAiModel(id: string, input: Partial<AiModel>): Promise<AiModel> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteAiModel(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
