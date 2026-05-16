# Core Concepts

## User

Global identity object.

A User represents a chat participant identity inside the system.

A user may represent:

- Human
- Persona

The User entity provides a unified identity layer for:

- permissions
- memberships
- chat participation
- mentions
- ownership
- audit history
- invite
- signed in
---

## Human

Private/authenticated representation of a real person.

Contains:

- email
- profile information
- timezone
- locale
- authentication data
- external identity mappings

Examples:

- Firebase identity
- Google SSO
- Microsoft SSO
- local authentication

A Human is always linked to exactly one User.

---

## Company

Tenant isolation and ownership boundary.

Everything belongs to a company.

Examples:

- projects
- models
- agents
- MCP servers
- personas
- knowledge bases
- users
- permissions

The Company provides:

- tenant isolation
- RBAC boundaries
- billing ownership
- deployment separation
- audit segregation
- models or agents ownership

---

## Project

Top-level collaboration workspace.

Projects organize collaborative work between:

- humans
- personas

A project contains:

- channels
- chat topics
- attached knowledge bases

Projects provide:

- scoped collaboration
- contextual AI workflows
- shared knowledge
- project-level permissions

---

## Channel

Logical collaboration grouping inside a project.

Channels separate discussions by:

- team
- domain
- workflow
- objective

Examples:

- Engineering
- Finance
- AI Research
- Customer Support

A channel contains:

- chat topics
- attached knowledge bases

---

## ChatTopic

Conversation or thread container.

A ChatTopic represents a focused discussion or task-oriented thread.

Examples:

- debugging session
- AI planning session
- invoice review
- code generation workflow

Contains:

- chat messages
- attached knowledge bases
- execution history
- contextual references

---

## ChatMessage

Atomic communication object inside a chat topic.

Stores:

- user messages
- AI responses
- tool outputs
- structured content
- forms
- graphs
- code blocks
- execution traces
- citations
- streaming chunks
- terminal output
- web view

Messages may contain:

- markdown
- JSON payloads
- rendered UI blocks
- MCP execution results

---

## AIModel

Represents a runtime model configuration.

Examples:

- GPT-4o
- Claude
- Ollama
- DeepSeek
- Azure OpenAI

Stores:

- provider
- model identifier
- runtime configuration
- token settings
- temperature settings
- secret references
- context limits
- endpoint configuration

An AIModel defines how inference is executed.

---

## MCPServer

Execution and tool integration backend.

Represents an MCP-compatible execution provider.

Can represent:

- local MCP server
- Docker MCP server
- Kubernetes MCP service
- remote HTTP MCP
- SSE MCP
- hosted MCP provider

Responsibilities include:

- tool discovery
- tool execution
- capability exposure
- external system integration
- infrastructure execution

Examples:

- ERP connector
- database executor
- filesystem tools
- Kubernetes operations
- browser automation

---

## AIAgent

Executable AI worker.

An AIAgent combines reasoning, execution, and workflow behavior.

Internal agent:

```text
AIModel + MCPServer + execution rules
```

External agent:

```text
Remote AI endpoint
```

An agent may:

- invoke tools
- perform autonomous workflows
- execute plans
- call external APIs
- collaborate with humans and personas

---

## Persona

User-facing AI identity.

A Persona behaves like a participant inside chats.

A Persona wraps either:

- AIModel
OR
- AIAgent

Personas provide:

- personality
- behavior rules
- communication style
- domain specialization
- persistent identity

Examples:

- DevOps Assistant
- ERP Accountant
- Research Analyst
- Islamic Scholar
- Coding Mentor

A Persona appears as a participant in chat conversations.

---

## KnowledgeBase

Reusable contextual knowledge container.

KnowledgeBases provide structured RAG context for projects and conversations.

Can attach to:

- Project
- Channel
- ChatTopic

Contains:

- KnowledgeFiles
- parsed content
- vectorized chunks
- metadata
- semantic indexes

Embeddings may be stored in:

- ChromaDB
- Qdrant
- OpenSearch
- future vector providers

---

## KnowledgeFile

Uploaded source document or dataset.

Examples:

- PDF
- DOCX
- TXT
- Markdown
- CSV
- JSON
- source code
- images

Files are processed through an ingestion pipeline:

```text
upload
→ parsing
→ chunking
→ embedding
→ vector storage
```

Additional processing may include:

- OCR
- metadata extraction
- AST parsing
- semantic enrichment
- language detection
- deduplication

# User Registration Stories

## Epic: User Registration & Identity Onboarding

Enable humans to create accounts, authenticate securely, join companies, and initialize their AI collaboration workspace.

---

# Sub Stories

## Story: Register Human Account

As a new user,  
I want to create a human account,  
So that I can access the platform securely.

### Acceptance Criteria

- User can register using email/password
- User can register using SSO providers
- System creates:
  - User
  - Human
  - default Company
- Email uniqueness is enforced
- Passwords are securely hashed
- Verification email may be sent
- Audit log is created

---

## Story: Login with Email & Password

As a registered user,  
I want to authenticate using my credentials,  
So that I can access my workspace.

### Acceptance Criteria

- User can login securely
- JWT/session token is issued
- Refresh token flow is supported
- Invalid credentials are rejected
- Login attempts are logged

---

## Story: Login with External SSO

As a user,  
I want to login using external providers,  
So that I can avoid managing passwords.

### Supported Providers

- Google
- Microsoft
- GitHub
- Apple
- Firebase Auth

### Acceptance Criteria

- OAuth login flow works
- Existing accounts can be linked
- New Human/User objects may be auto-created
- Secure token validation is enforced

---

## Story: Create Default Company

As a newly registered user,  
I want a default company workspace created automatically,  
So that I can start collaborating immediately.

### Acceptance Criteria

- Default company is created
- Human becomes company owner
- Default permissions are assigned
- Default project may optionally be created

---

## Story: Initialize Default Workspace

As a new user,  
I want starter collaboration resources,  
So that I can begin using the platform quickly.

### Acceptance Criteria

System may create:

- default project
- general channel
- onboarding chat topic
- starter persona
- starter knowledge base

---

## Story: Verify Email Address

As a platform administrator,  
I want users to verify their email addresses,  
So that fake or invalid registrations are reduced.

### Acceptance Criteria

- Verification token is generated
- Verification email is sent
- Token expiration is enforced
- Email becomes verified after confirmation

---

## Story: Reset Forgotten Password

As a user,  
I want to reset my password securely,  
So that I can regain account access.

### Acceptance Criteria

- Reset token is generated
- Token expiration is enforced
- Password reset link is emailed
- Old tokens become invalid after reset

---

## Story: Invite User to Company

As a company administrator,  
I want to invite users into my company,  
So that they can collaborate inside shared projects.

### Acceptance Criteria

- Invitation email is generated
- Role can be preassigned
- User may accept or reject invitation
- Existing users can join directly
- New users may register from invitation flow

---

## Story: Multi-Company Membership

As a user,  
I want to belong to multiple companies,  
So that I can collaborate across organizations.

### Acceptance Criteria

- Human may belong to multiple companies
- Active company can be switched
- Permissions are isolated per company
- Company context is enforced in APIs

---

## Story: User Profile Management

As a user,  
I want to manage my profile information,  
So that my preferences and identity remain accurate.

### Acceptance Criteria

User can update:

- display name
- timezone
- locale
- avatar
- notification preferences

---

## Story: Session Management

As a user,  
I want secure session handling,  
So that my account remains protected.

### Acceptance Criteria

- Sessions can be revoked
- Multiple active sessions are supported
- Device tracking may be supported
- Token expiration is enforced

---

## Story: Role & Permission Initialization

As the system,  
I want default roles and permissions assigned during onboarding,  
So that access control works immediately.

### Acceptance Criteria

Default roles may include:

- Owner
- Admin
- Member
- Viewer

Default permission mappings are initialized automatically.


# Chat Messaging Stories

## Epic: Send Message to Chat Topic

Enable humans, personas, AI models, and agents to participate in a ChatTopic by sending messages with different output formats.

---

## Story: Human Sends Message to Chat Topic

As a human user,  
I want to send a message inside a ChatTopic,  
So that I can collaborate with other humans, personas, or agents.

### Flow

```text
User sends message to ChatTopic
→ validate user has company access
→ validate user has project/channel/topic access
→ create ChatMessage(status=completed, sender=user)
→ broadcast message to topic participants
→ emit event to AI service if AI persona/agent is active in topic
```

### Acceptance Criteria

- User must belong to the company
- User must have access to the project
- User must have access to the channel/topic
- Message is stored as `ChatMessage`
- Sender is recorded as human user
- Message status is set to `completed`
- Message is broadcast to active topic subscribers
- AI processing event is triggered when required

---

## Story: AI Model Sends Message

As the system,  
I want an AI model to send messages into a ChatTopic,  
So that users can receive AI-generated responses.

### Flow

```text
AI service receives user message event
→ load topic context
→ load attached knowledge bases
→ call AIModel
→ create ChatMessage(sender=ai_model, status=completed)
→ broadcast AI message
```

### Acceptance Criteria

- AIModel must belong to the same company
- AIModel must be allowed in the project/topic
- AI response is saved as ChatMessage
- Sender type is recorded as `ai_model`
- Token usage may be stored
- Model configuration is recorded
- Errors are saved as failed messages

---

## Story: AI Agent Sends Message

As an AI agent,  
I want to send messages into a ChatTopic,  
So that I can execute workflows and return useful results.

### Flow

```text
Agent receives task/context
→ load AIModel
→ load MCPServer/tools
→ execute reasoning or tools
→ create ChatMessage(sender=agent)
→ store tool outputs if used
→ broadcast final response
```

### Acceptance Criteria

- Agent must belong to the company
- Agent must have permission to participate in topic
- Agent execution rules are enforced
- MCP/tool calls are logged
- Final agent response is stored as ChatMessage
- Intermediate outputs may be stored as execution traces

---

## Story: Persona Sends Message

As a persona,  
I want to participate like a chat member,  
So that humans can interact with specialized AI identities.

### Acceptance Criteria

- Persona appears as a chat participant
- Persona may wrap an AIModel or AIAgent
- Persona messages are stored as ChatMessage
- Persona identity is visible in UI
- Persona behavior follows configured system prompt/rules

---

## Story: Store Message Output Format

As the system,  
I want each ChatMessage to support multiple output formats,  
So that AI and tools can return rich interactive content.

### Supported Output Formats

- text
- markdown
- code
- terminal output
- graph
- form
- diagram
- table
- JSON
- web view
- tool output
- file reference

### Acceptance Criteria

- Message has `content_type` or `output_format`
- Message payload supports structured JSON
- UI can render different message types
- Unsupported formats fall back to raw JSON/text
- Message metadata stores renderer hints

---

## Story: Send Text Message

As a sender,  
I want to send plain text or markdown,  
So that normal conversation works.

### Acceptance Criteria

- Text is stored safely
- Markdown may be rendered in UI
- Unsafe HTML/scripts are sanitized
- Mentions and references may be parsed

---

## Story: Send Code Output

As an AI model or agent,  
I want to return code blocks,  
So that users can copy and review generated code.

### Acceptance Criteria

- Code language is stored
- Code block is rendered with formatting
- Copy action is supported
- Multiple code blocks may exist in one message

---

## Story: Send Terminal Output

As an agent,  
I want to return terminal output,  
So that users can see command execution results.

### Acceptance Criteria

- Command output is stored separately from normal text
- stdout and stderr may be stored
- exit code may be stored
- command metadata may be attached
- sensitive values are masked when required

---

## Story: Send Graph Output

As an AI model or agent,  
I want to return graph data,  
So that the UI can visualize results.

### Acceptance Criteria

- Graph type is stored
- Graph data is stored as structured JSON
- Supported graph types may include:
  - bar chart
  - line chart
  - pie chart
  - network graph
  - workflow graph
- UI renders graph from message payload

---

## Story: Send Form Output

As an AI agent,  
I want to return an interactive form,  
So that users can review, approve, or submit structured data.

### Acceptance Criteria

- Form schema is stored as JSON
- Form fields include labels, types, and validation rules
- User can submit form response
- Submitted form creates a follow-up ChatMessage or workflow event
- Form can be used for approval workflows

---

## Story: Send Diagram Output

As an AI model or agent,  
I want to return diagrams,  
So that users can understand architecture, workflows, or relationships.

### Acceptance Criteria

- Diagram source is stored
- Supported formats may include:
  - Mermaid
  - PlantUML
  - SVG
  - JSON graph schema
- UI renders diagram safely
- Raw diagram source can be viewed

---

## Story: Send Web View Output

As an AI agent,  
I want to return a web view,  
So that users can interact with external or internal pages inside chat.

### Acceptance Criteria

- Web view URL or embedded app reference is stored
- Allowed domains are validated
- Unsafe URLs are blocked
- Web view permissions are enforced
- UI renders web view in controlled container

---

## Story: Send Tool Output Message

As an MCP tool,  
I want to return execution output into chat,  
So that users can see what happened during tool execution.

### Acceptance Criteria

- Tool output is linked to MCP execution record
- Tool name and server are stored
- Tool input and output may be stored
- Sensitive fields can be redacted
- Tool success/failure status is recorded

---

## Story: Stream AI Message

As a user,  
I want AI responses to stream gradually,  
So that I can see progress while the model is generating.

### Flow

```text
AI starts generating
→ create ChatMessage(status=streaming)
→ append chunks
→ broadcast chunks by SSE/WebSocket
→ mark ChatMessage(status=completed)
```

### Acceptance Criteria

- Streaming message is created before completion
- Chunks are appended in order
- UI receives real-time updates
- Final message is stored
- Failed stream is marked as failed

---

## Story: Handle Message Failure

As the system,  
I want failed AI or agent messages to be stored clearly,  
So that users can understand what went wrong.

### Acceptance Criteria

- Failed message has `status=failed`
- Error summary is stored
- Internal error details may be hidden from user
- Retry may be supported
- Failure is logged for debugging

---

## Story: Trigger AI Processing After User Message

As the system,  
I want to trigger AI processing when a user sends a message,  
So that active personas or agents can respond automatically.

### Trigger Conditions

AI processing may start when:

- topic has active AI persona
- topic has assigned agent
- user explicitly mentions a persona/agent
- user uses command syntax
- workflow is waiting for user input

### Acceptance Criteria

- AI trigger rules are evaluated
- Correct AIModel/Persona/Agent is selected
- Topic context is loaded
- KnowledgeBase context is injected
- AI response job is created
- Duplicate AI jobs are avoided

# AI Model Management Stories

## Epic: AI Model Management

Enable companies to configure and manage reusable AI runtime models securely across projects, personas, and agents.

---

## Story: Create AI Model

As a company user,  
I want to create an AIModel configuration,  
So that personas and agents can use AI providers securely.

### Flow

```text
User creates AIModel under Company
→ validate permissions
→ validate provider configuration
→ store provider/model_id/runtime config
→ store secret_ref instead of raw API key
→ create AIModel
```

### Acceptance Criteria

- AIModel belongs to a Company
- User must have permission to create models
- Provider type is validated
- model_id is required
- Runtime configuration is stored
- API secrets are never stored directly in plaintext
- Only secret references are persisted
- Audit log is created

---

## Story: Configure AI Provider Settings

As a user,  
I want to configure provider-specific settings,  
So that models behave correctly for different runtimes.

### Supported Providers

- OpenAI
- Azure OpenAI
- Anthropic
- Ollama
- DeepSeek
- OpenRouter
- Gemini
- future providers

### Acceptance Criteria

Provider configuration may include:

- endpoint URL
- API version
- deployment name
- organization ID
- region
- custom headers

Validation rules differ by provider.

---

## Story: Configure Runtime Parameters

As a user,  
I want to configure runtime behavior,  
So that AI inference matches my workflow requirements.

### Acceptance Criteria

Runtime settings may include:

- temperature
- top_p
- max_tokens
- context_window
- stop sequences
- streaming enabled
- reasoning mode
- timeout settings

System validates parameter ranges.

---

## Story: Secure Secret Management

As the system,  
I want API secrets handled securely,  
So that credentials are never exposed.

### Flow

```text
User submits provider credentials
→ credentials stored in secret manager
→ generate secret_ref
→ AIModel stores secret_ref only
```

### Acceptance Criteria

- Raw API keys are never stored in database
- Secret references are encrypted
- Secret manager integration is supported
- Secret rotation may be supported
- Secrets are masked in UI and logs
- Access to secrets is permission controlled

### Supported Secret Backends

- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Kubernetes Secrets
- environment variables
- local encrypted storage

---

## Story: Validate AI Model Connectivity

As a user,  
I want to test AIModel connectivity,  
So that I can confirm configuration works.

### Flow

```text
User clicks test connection
→ load provider config
→ resolve secret_ref
→ perform lightweight inference/test request
→ return success or failure
```

### Acceptance Criteria

- Connectivity test does not expose secrets
- Errors are sanitized
- Latency may be recorded
- Supported features may be detected
- Validation result is stored optionally

---

## Story: Enable Streaming Support

As a user,  
I want AIModels to support streaming responses,  
So that chat responses appear in real time.

### Acceptance Criteria

- AIModel may enable or disable streaming
- SSE/WebSocket compatible providers are supported
- Chunked token streaming is supported
- Streaming capability is provider-aware

---

## Story: Configure Model Visibility

As a company administrator,  
I want to control which users/projects can access AIModels,  
So that model usage remains secure.

### Acceptance Criteria

AIModel visibility may be:

- private
- company-wide
- project-scoped
- role-scoped

Permission enforcement is applied during inference.

---

## Story: Attach AIModel to Persona

As a user,  
I want to attach an AIModel to a Persona,  
So that the Persona can generate responses.

### Acceptance Criteria

- Persona can reference exactly one active AIModel
- AIModel and Persona belong to same Company
- Runtime overrides may be supported
- Persona inherits AIModel capabilities

---

## Story: Attach AIModel to AIAgent

As a user,  
I want an AIAgent to use an AIModel,  
So that the agent can perform reasoning.

### Acceptance Criteria

- Agent references AIModel
- AIModel configuration is loaded during execution
- Agent may override runtime parameters
- Missing or disabled models block execution

---

## Story: Disable AI Model

As an administrator,  
I want to disable an AIModel temporarily,  
So that inference can be stopped without deleting configuration.

### Acceptance Criteria

- Disabled models cannot be used
- Existing history remains intact
- Personas/agents referencing disabled models show warnings
- Re-enable is supported

---

## Story: Delete AI Model

As a user,  
I want to remove unused AIModels,  
So that old configurations do not clutter the system.

### Acceptance Criteria

- Soft delete may be supported
- Dependency validation occurs before deletion
- Active personas/agents prevent hard delete
- Audit trail remains preserved

---

## Story: Track AI Model Usage

As a company administrator,  
I want to track model usage,  
So that costs and consumption can be monitored.

### Acceptance Criteria

Usage metrics may include:

- token usage
- request count
- latency
- failure count
- provider costs
- user/project usage breakdown

Usage records are linked to:

- ChatMessages
- Personas
- Agents
- Projects

---

## Story: Support Local AI Models

As a user,  
I want to use local/self-hosted models,  
So that I maintain full data control.

### Acceptance Criteria

Supported runtimes may include:

- Ollama
- vLLM
- llama.cpp
- TGI
- custom HTTP runtimes

Local endpoints may run:

- on desktop
- inside Docker
- inside Kubernetes
- on remote GPU clusters

---

## Story: Support Multi-Provider Fallback

As the system,  
I want fallback model execution,  
So that failures do not interrupt workflows.

### Flow

```text
Primary model fails
→ evaluate fallback rules
→ retry with fallback AIModel
→ record failover event
```

### Acceptance Criteria

- Fallback chains are configurable
- Retry limits are enforced
- Provider failures are logged
- User may see failover status
- Cost tracking remains accurate

# AI Agent Management Stories

## Epic: AI Agent Management

Enable users to create executable AI workers by combining AI models, MCP/tool backends, external endpoints, and execution rules.

---

## Story: Create AI Agent

As a company user,  
I want to create an AIAgent,  
So that I can automate tasks and execute workflows inside projects and chat topics.

### Flow

```text
User selects AIModel
→ selects MCPServer or external agent URL
→ defines execution rules
→ creates AIAgent
→ agent = model + MCP server + execution rules
```

### Acceptance Criteria

- User must have permission to create agents
- AIAgent belongs to a Company
- AIModel belongs to same Company
- MCPServer belongs to same Company, if selected
- External agent URL is validated, if used
- Agent name is required
- Agent status is set to active or draft
- Audit log is created

---

## Story: Create Internal Agent

As a user,  
I want to create an internal agent from an AIModel and MCPServer,  
So that the agent can reason and execute tools.

### Flow

```text
User selects AIModel
→ user selects MCPServer
→ user defines system instructions
→ user defines execution limits
→ system creates internal AIAgent
```

### Acceptance Criteria

- Internal agent requires AIModel
- MCPServer is optional but required for tool execution
- Execution rules are stored
- Tool permissions are enforced
- Agent can be attached to personas or chat topics

---

## Story: Create External Agent

As a user,  
I want to register an external agent endpoint,  
So that NeuralOps can call agents hosted outside the platform.

### Flow

```text
User enters external agent URL
→ system validates endpoint
→ user defines authentication secret_ref
→ system creates external AIAgent
```

### Acceptance Criteria

- External URL must be valid
- Authentication uses `secret_ref`
- Raw API keys are not stored
- Health check may be performed
- External agent response schema is validated

---

## Story: Define Agent Execution Rules

As a user,  
I want to configure agent execution rules,  
So that the agent works safely and predictably.

### Execution Rules May Include

- max tool calls
- max runtime duration
- allowed tools
- blocked tools
- approval required before tool execution
- read-only mode
- retry limits
- escalation rules
- output format rules

### Acceptance Criteria

- Rules are stored as structured configuration
- Unsafe rules are rejected
- Defaults are applied when missing
- Rules are enforced during execution

---

## Story: Attach MCPServer to Agent

As a user,  
I want to attach an MCPServer to an AIAgent,  
So that the agent can discover and execute tools.

### Acceptance Criteria

- MCPServer must belong to same Company
- MCPServer must be active
- Tool discovery can be performed
- Agent stores MCPServer reference
- Agent execution loads MCP tools dynamically

---

## Story: Configure Agent System Instructions

As a user,  
I want to define system instructions for an agent,  
So that the agent follows a specific role and behavior.

### Acceptance Criteria

- Instructions are stored with the agent
- Instructions are injected during execution
- Instructions may include domain rules
- Instructions may include safety limits
- Versioning may be supported

---

## Story: Test Agent Execution

As a user,  
I want to test an AIAgent before using it in production,  
So that I can verify model, tools, and rules work correctly.

### Flow

```text
User sends test prompt
→ system loads AIModel
→ system loads MCPServer/tools
→ system applies execution rules
→ agent runs in test mode
→ result is returned
```

### Acceptance Criteria

- Test execution does not affect production data unless allowed
- Tool execution can be mocked or read-only
- Errors are shown safely
- Execution logs are stored optionally

---

## Story: Agent Sends Chat Message

As an AIAgent,  
I want to send messages into a ChatTopic,  
So that I can return results to users.

### Acceptance Criteria

- Agent must have access to the topic
- Agent output is stored as ChatMessage
- Sender type is recorded as `agent`
- Output format may be text, code, graph, form, terminal output, diagram, or web view
- Tool outputs may be linked to the message

---

## Story: Control Agent Availability

As an administrator,  
I want to enable or disable agents,  
So that unsafe or unused agents cannot execute.

### Acceptance Criteria

- Disabled agents cannot run
- Existing chat history remains preserved
- Personas using disabled agents show warnings
- Re-enable is supported

---

## Story: Track Agent Execution

As a company administrator,  
I want to track agent execution history,  
So that I can audit actions and debug failures.

### Acceptance Criteria

Execution logs may include:

- agent ID
- model ID
- MCP server ID
- user/topic trigger
- tool calls
- input summary
- output summary
- status
- error details
- duration
- token usage

# Invitation & Membership Stories

## Epic: Invite User

Enable company members to invite humans into a company, project, or channel with correct access boundaries.

---

## Story: Invite User to Company

As a company admin,  
I want to invite a user to my company,  
So that they can access company resources.

### Flow

```text
Invite user to company
→ validate inviter permission
→ create invitation
→ create CompanyAccess after acceptance
→ assign company role
```

### Acceptance Criteria

- Inviter must have permission to invite users
- Invitation can be sent to existing or new users
- Email address is required
- Company role is selected
- Duplicate active invitations are prevented
- User receives invitation
- CompanyAccess is created after acceptance
- Audit log is created

---

## Story: Invite User to Project

As a project admin,  
I want to invite a user to a project,  
So that they can collaborate inside that project.

### Flow

```text
Invite user to project
→ create CompanyAccess if needed
→ create ProjectMember after acceptance
→ assign project role
```

### Acceptance Criteria

- Inviter must have project invite permission
- If user is not in company, company access is created after acceptance
- ProjectMember is created after acceptance
- Project role is assigned
- Project must belong to same company
- Invitation cannot cross company boundary

---

## Story: Invite User to Channel

As a channel admin,  
I want to invite a user to a channel,  
So that they can participate in channel discussions.

### Flow

```text
Invite user to channel
→ create CompanyAccess if needed
→ create ProjectMember if needed
→ create ChannelMember after acceptance
```

### Acceptance Criteria

- Inviter must have channel invite permission
- User must have or receive company access
- User must have or receive project membership
- ChannelMember is created after acceptance
- Channel must belong to same project/company
- Private channel access is enforced

---

## Story: Accept Invitation

As an invited user,  
I want to accept an invitation,  
So that I can join the company, project, or channel.

### Flow

```text
User opens invitation
→ validate token
→ validate expiration
→ create missing access records
→ mark invitation as accepted
```

### Acceptance Criteria

- Invitation token is valid
- Expired invitations are rejected
- Already accepted invitations cannot be reused
- Required memberships are created
- Correct role is assigned
- User is redirected to target resource

---

## Story: Invite New User Who Has No Account

As an invited person,  
I want to register from an invitation,  
So that I can join the correct workspace immediately.

### Flow

```text
User opens invitation link
→ user registers account
→ create User/Human
→ accept invitation
→ create CompanyAccess/ProjectMember/ChannelMember
```

### Acceptance Criteria

- Invitation email is prefilled
- New account is linked to invitation
- User cannot accept invitation with a different email unless allowed
- Membership records are created after registration
- User lands in invited project/channel

---

## Story: Reject Invitation

As an invited user,  
I want to reject an invitation,  
So that I am not added to the workspace.

### Acceptance Criteria

- Invitation can be rejected
- No access records are created
- Invitation status becomes rejected
- Inviter may be notified

---

## Story: Revoke Pending Invitation

As an admin,  
I want to revoke an invitation,  
So that pending access can be cancelled.

### Acceptance Criteria

- Only pending invitations can be revoked
- Revoked invitations cannot be accepted
- Revocation is audited
- Invited user may be notified

---

## Story: Prevent Duplicate Memberships

As the system,  
I want to prevent duplicate access records,  
So that membership data stays clean.

### Acceptance Criteria

- Duplicate CompanyAccess records are prevented
- Duplicate ProjectMember records are prevented
- Duplicate ChannelMember records are prevented
- Existing membership may be updated instead of recreated

---

## Story: Assign Invitation Roles

As an inviter,  
I want to assign roles during invitation,  
So that invited users receive correct permissions.

### Role Scope

Roles may apply to:

- company
- project
- channel

### Acceptance Criteria

- Role must belong to correct scope
- Inviter cannot assign a role higher than their own permission level
- Default role is applied when no role is selected
- Role assignment is stored with invitation

---

## Story: Audit Invitation Lifecycle

As a company administrator,  
I want invitation events logged,  
So that access changes are traceable.

### Events

- invitation created
- invitation sent
- invitation accepted
- invitation rejected
- invitation revoked
- invitation expired

### Acceptance Criteria

- Actor is recorded
- Target email/user is recorded
- Scope is recorded
- Timestamp is recorded
- Result status is recorded


# Knowledge Context Stories

## Epic: Upload Knowledge Context

Enable users to upload reusable knowledge, process files into searchable embeddings, and attach knowledge context to projects, channels, or chat topics.

---

## Story: Create KnowledgeBase

As a user,  
I want to create a KnowledgeBase,  
So that I can organize reusable context for AI conversations.

### Flow

```text
User creates KnowledgeBase
→ validate company/project access
→ create KnowledgeBase under Company
→ optionally attach to Project/Channel/ChatTopic
```

### Acceptance Criteria

- User must have permission to create knowledge bases
- KnowledgeBase belongs to a Company
- KnowledgeBase has name and description
- Visibility/access scope is stored
- Audit log is created

---

## Story: Upload KnowledgeFile

As a user,  
I want to upload files into a KnowledgeBase,  
So that AI models and agents can use them as context.

### Flow

```text
User uploads KnowledgeFile
→ validate file type and size
→ store original file
→ create KnowledgeFile(status=uploaded)
→ enqueue parsing/chunking/embedding job
```

### Acceptance Criteria

- File belongs to a KnowledgeBase
- Supported file types are accepted
- Unsupported file types are rejected
- File size limit is enforced
- Original file is stored safely
- Processing job is created

---

## Story: Process KnowledgeFile

As the system,  
I want to parse, chunk, and embed uploaded files,  
So that they become searchable context.

### Flow

```text
KnowledgeFile uploaded
→ parse file content
→ extract metadata
→ split into chunks
→ generate embeddings
→ store chunks in ChromaDB
→ mark KnowledgeFile(status=processed)
```

### Acceptance Criteria

- File status changes during processing
- Parsed text is extracted
- Metadata is preserved
- Chunks are created
- Embeddings are generated
- Vector records are linked to KnowledgeFile
- Failed processing marks file as failed

---

## Story: Attach KnowledgeBase to Project

As a project member,  
I want to attach a KnowledgeBase to a Project,  
So that all project conversations can use shared context.

### Acceptance Criteria

- User must have project permission
- KnowledgeBase and Project belong to same Company
- Duplicate attachment is prevented
- Project-level AI context includes attached KnowledgeBase

---

## Story: Attach KnowledgeBase to Channel

As a channel member,  
I want to attach a KnowledgeBase to a Channel,  
So that channel discussions can use relevant context.

### Acceptance Criteria

- User must have channel permission
- Channel belongs to same Company as KnowledgeBase
- Duplicate attachment is prevented
- Channel context inherits project context if configured

---

## Story: Attach KnowledgeBase to ChatTopic

As a user,  
I want to attach a KnowledgeBase to a ChatTopic,  
So that one conversation can use specific context.

### Acceptance Criteria

- User must have topic permission
- ChatTopic belongs to same Company as KnowledgeBase
- Duplicate attachment is prevented
- Topic-level context has highest priority

---

## Story: Retrieve Knowledge Context for AI

As the AI service,  
I want to retrieve relevant chunks from attached KnowledgeBases,  
So that AI responses are grounded in selected context.

### Flow

```text
User message received
→ resolve Project/Channel/ChatTopic KnowledgeBases
→ embed query
→ search ChromaDB
→ rank relevant chunks
→ inject selected context into AI prompt
```

### Acceptance Criteria

- Only authorized KnowledgeBases are searched
- Project, Channel, and ChatTopic attachments are resolved
- Query embedding is generated
- Relevant chunks are returned
- Context limits are respected
- Retrieved chunks are linked to AI response metadata

---

## Story: Handle KnowledgeFile Processing Failure

As the system,  
I want to record failed file processing clearly,  
So that users can fix upload or parsing problems.

### Acceptance Criteria

- Failed file has `status=failed`
- Error summary is stored
- Retry processing is supported
- Original file remains available
- User can delete or replace failed file

---

## Story: Delete KnowledgeFile

As a user,  
I want to remove a KnowledgeFile,  
So that outdated context is no longer used.

### Acceptance Criteria

- File can be soft deleted
- Related vector chunks are removed or disabled
- Existing chat history remains preserved
- Deletion is audited

---

## Story: Reprocess KnowledgeFile

As a user,  
I want to reprocess a KnowledgeFile,  
So that updated parsing/chunking/embedding logic can be applied.

### Acceptance Criteria

- Reprocess action creates new chunks
- Old chunks are replaced or versioned
- File status updates during processing
- Failed reprocessing preserves previous usable version if configured