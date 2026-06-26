export interface Company { id: string; name: string }
export interface User { id: string; email: string; name?: string }
export interface Project { id: string; companyId: string; name: string }
export interface Channel { id: string; projectId: string; name: string }
export interface Topic { id: string; channelId: string; name: string }
export interface Message { id: string; topicId: string; content: string; createdAt: string }
export interface Agent { id: string; name: string; description?: string }
export interface Persona { id: string; name: string; description?: string }
export interface AiModel { id: string; name: string; provider: string }
export interface McpServer { id: string; name: string; url: string }
export interface KnowledgeBaseItem { id: string; title: string }
export interface Notification { id: string; message: string; read: boolean; createdAt: string }
