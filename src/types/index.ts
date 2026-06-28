// Shared types used across services. Refine as the Django API solidifies.

export interface Company {
  id: string;
  name: string;
  slug?: string;
}

export interface User {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
}

export interface Project {
  id: string;
  company_id: string;
  name: string;
  description?: string;
}

export interface Channel {
  id: string;
  project_id: string;
  name: string;
}

export interface Topic {
  id: string;
  channel_id: string;
  title: string;
  updated_at?: string;
}

export interface Message {
  id: string;
  topic_id: string;
  role: "user" | "assistant" | "agent" | "system";
  content: string;
  author_id?: string;
  created_at?: string;
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  persona_id?: string;
  model_id?: string;
}

export interface Persona {
  id: string;
  name: string;
  system_prompt?: string;
}

export interface AIModel {
  id: string;
  name: string;
  provider: string;
}

export interface MCPServer {
  id: string;
  name: string;
  url: string;
}

export interface KnowledgeItem {
  id: string;
  title: string;
  content?: string;
}

export interface Notification {
  id: string;
  title: string;
  body?: string;
  read: boolean;
  created_at?: string;
}

export interface ServerEntry {
  id: string;
  name: string;
  url: string;
}
