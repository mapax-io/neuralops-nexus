import { apiJson } from "./api.client";
import type { MCPServer } from "@/types";

export async function listMCPServers(): Promise<MCPServer[]> {
  return apiJson<MCPServer[]>("/api/v1/mcp-servers/");
}

export async function createMCPServer(
  input: Partial<MCPServer>,
): Promise<MCPServer> {
  return apiJson<MCPServer>("/api/v1/mcp-servers/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
