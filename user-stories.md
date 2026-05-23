# NeuralOPS Nexus — Core Context & Workflow Notes

## Version

- Architecture Version: `1.0.0-alpha`
- ORM: `Django ORM`
- Database: `PostgreSQL`
- Vector Store: `ChromaDB`
- AI Gateway: `LiteLLM`
- Deployment Targets:
  - Local
  - Docker
  - Kubernetes
  - Cloud
  - Enterprise Private Cluster

---

# Core Concepts

## User

Global identity object.

A user may represent:

- Human
- Persona

---

## Human

Private/authenticated side of a real user.

Contains:

- email
- profile
- timezone
- locale
- authentication data

---

## Company

Tenant/workspace boundary.

Everything belongs to a company:

- projects
- models
- agents
- MCP servers
- personas
- knowledge bases

---

## Project

Top-level collaboration workspace.

Contains:

- channels
- chat topics
- attached knowledge bases

---

## Channel

Logical collaboration grouping inside project.

Contains:

- chat topics
- attached knowledge bases

---

## ChatTopic

Conversation/thread container.

Contains:

- messages
- attached knowledge bases

---

## ChatMessage

Stores:

- user messages
- AI messages
- tool outputs
- structured content
- forms
- graphs
- code blocks

---

## AIModel

Represents runtime model configuration.

Examples:

- GPT-4o
- Claude
- Ollama
- DeepSeek
- Azure OpenAI

Stores:

- provider
- model_id
- runtime configuration
- token settings
- secret references

---

## MCPServer

Execution/tool backend.

Can represent:

- local MCP server
- Docker MCP server
- Kubernetes MCP service
- remote HTTP MCP
- SSE MCP
- hosted MCP provider

---

## AIAgent

Executable AI worker.

Internal agent:

```text
AIModel + MCPServer + execution rules
```

External agent:

```text
Remote AI endpoint
```

---

## Persona

User-like AI identity.

Persona wraps:

- AIModel
OR
- AIAgent

Persona appears as a participant in chat.

---

## KnowledgeBase

Reusable contextual knowledge container.

Can attach to:

- Project
- Channel
- ChatTopic

Contains:

- KnowledgeFiles
- vectorized chunks in ChromaDB

---

## KnowledgeFile

Uploaded source file.

Examples:

- PDF
- DOCX
- TXT
- Markdown
- CSV
- JSON
- Codebase files

Files are:

```text
uploaded
→ parsed
→ chunked
→ embedded
→ stored in ChromaDB
```

---

# Core Use Cases

---

## Register Google User

```text
Google login received
→ create/find User
→ create/find Human profile
→ create/find personal Company
→ create CompanyAccess as owner
→ set User.current_company
```

---

## Send Message to Chat Topic

```text
User sends message to ChatTopic
→ validate user has company/project access
→ create ChatMessage(status=completed, sender=user)
→ emit event to AI service if topic has AI persona/agent involved
```

---

## Create AI Model

```text
User creates AIModel under Company
→ store provider/model_id/runtime config
→ store secret_ref, not raw API key
```

---

## Create AI Agent

```text
User selects AIModel
→ selects MCPServer or external agent URL
→ creates AIAgent
→ agent = model + MCP server + execution rules
```

---

## Invite User

```text
Invite user to company/project/channel
→ create CompanyAccess if needed
→ create ProjectMember
→ optionally create ChannelMember
```

---

## Upload Knowledge Context

```text
User creates/uploads KnowledgeBase + KnowledgeFile
→ file is parsed/chunked/embedded into ChromaDB
→ KnowledgeBase attached to Project/Channel/ChatTopic
```

---

# AI Message Processing Flow

```text
User Message
→ Save ChatMessage
→ Resolve active KBs from project/channel/topic
→ Embed user query
→ Chroma search with:
      company_id = current_company_id
      knowledge_base_id IN active_kb_ids
→ Get top K chunks
→ Load recent chat history
→ Load persona system prompt

→ If persona wraps agent:
      load agent system prompt
      load model
      load MCP server

→ Build final prompt
→ Send to model
→ Save AI answer as ChatMessage(sender=persona.identity_user)
```

---

# Context Resolution Strategy

## Django Database Responsibilities

Django/PostgreSQL decides:

```text
WHICH knowledge bases are active
```

Based on:

- project
- channel
- chat topic

---

## ChromaDB Responsibilities

ChromaDB decides:

```text
WHICH chunks inside active KBs are relevant
```

---

# Active Context Resolution

```python
active_kbs =
    project.knowledge_bases
  + channel.knowledge_bases
  + topic.knowledge_bases
```

---

# Suggested Chroma Metadata

```json
{
  "company_id": "...",
  "knowledge_base_id": "...",
  "knowledge_file_id": "...",
  "source": "document.pdf",
  "chunk_index": 12
}
```

---

# Suggested Service Layer

## ChatService

Handles:

- chat creation
- message persistence
- permissions
- streaming events

---

## KnowledgeContextResolver

Resolves active knowledge bases from:

- project
- channel
- topic

---

## VectorSearchService

Handles:

- embeddings
- Chroma queries
- semantic search

---

## PromptBuilderService

Builds final prompt using:

- system prompts
- history
- retrieved chunks
- persona
- agent configuration

---

## AIOrchestratorService

Responsible for:

- model execution
- MCP execution
- streaming
- retries
- external agent calls

---

# Architectural Principle

```text
Django DB decides WHICH knowledge bases are active.
ChromaDB decides WHICH chunks inside those knowledge bases are relevant.
```