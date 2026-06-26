import type { McpServer } from "@/types";

// TODO: implement API calls for mcp-servers
export function listMcpServers(): Promise<McpServer[]> {
  throw new Error("Not implemented");
}

export function getMcpServer(id: string): Promise<McpServer> {
  void id;
  throw new Error("Not implemented");
}

export function createMcpServer(input: Partial<McpServer>): Promise<McpServer> {
  void input;
  throw new Error("Not implemented");
}

export function updateMcpServer(id: string, input: Partial<McpServer>): Promise<McpServer> {
  void id; void input;
  throw new Error("Not implemented");
}

export function deleteMcpServer(id: string): Promise<void> {
  void id;
  throw new Error("Not implemented");
}
