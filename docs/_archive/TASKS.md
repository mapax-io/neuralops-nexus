# NeuralOps Task List

Full development task history for neuralops-staging, tracked chronologically.
Generated from the session task tracker — last updated 2026-08-07.

## Open / Backlog

| # | Task | Notes |
|---|------|-------|
| 22 | Re-embedding Celery task on embedder switch | Held — nexus-ai owner will decide |
| 121 | Rights-check decorator to replace scattered `PermissionChecker.can()` calls | Held — deferred, revisit later |
| 143 | Refactor docker-compose to env-driven container naming | Single compose file, `container_name: ${CONTAINER_PREFIX:-nexus}-nucleus` style, instead of the current base+staging-override two-file pattern |
| 145 | Persona chaining (`@chain @A @B @C`) | Fully spec'd: 3-4 distinct personas, single-pass sequential, each step posts a real visible message, one-shot trigger |
| 146 | Chain + session persistence | Deferred layer on top of #145 — an opened chain keeps re-triggering on future plain messages, like `@session` does |
| 147 | Default per-project output folder + save-to-disk | Organized by topic slug; right-click-save AI output to disk, later downloadable |
| 149 | Prompt building design pass | Rework of PromptBuilder in nexus-ai — not yet scoped in detail |
| 150 | MCP servers focus pass | Not yet scoped in detail |
| 169 | Add file context type | Split off from #141 — keep separate from typing/thinking indicators |
| 171 | Library of system prompt templates (hundreds) for personas | `PromptTemplate` model already exists — needs content (hundreds of starter prompts) + search/category filtering in `list_prompt_templates()`, which currently only sorts by `-is_featured, title` |

## Completed

### M1 — Foundation
1. Show sent time on messages
2. Add unread dot to topic sidebar
3. Add message beep notification
4. Render Markdown and code blocks in messages
5. AI streaming spike — backend (dev_ai_spike.py + urls.py)
6. AI streaming spike — frontend (useChat.ts + chat.service.ts)
7. Fix AgentRunner interface — pass messages directly
8. Fix ChromaDB sync calls — wrap with asyncio.to_thread
9. Fix Ollama URL + add LLM_MODEL to config
10. Clean up requirements.txt and remove schemas.py
11. Write complete flow + milestones document
12. Remove [anthropic] from pydantic-ai-slim in requirements.txt
13. Simplify EmbeddingFactory — remove ollama/openai cases
14. Delete ollama_embedding.py and openai_embedding.py
15. Fix AIModel.Provider enum — collapse to LITELLM + LOCAL
16. Fix nexus-ai config.py — clean EMBEDDING_MODEL default and comments
17. Fix docker-compose.yaml — clean EMBEDDING_MODEL default and remove OLLAMA_API_BASE from nucleus
18. M1 testing — curl through all endpoints

### M2 — Message embedding
19. Fix ChatMessage sequence auto-increment
20. Add fire-and-forget embed call in nucleus after message save
21. Build /embed/message/ endpoint in nexus-ai

### M3 — AI trigger + persona mentions
23. Add litellm extra to pydantic-ai requirements
24. Update TriggerJob ModelConfig — add api_key, fix provider
25. Update PydanticAIRunner to use LiteLLMModel
26. Add get_persona_by_mention() to intelligence_services
27. Add trigger_ai_response_async() to chat_services
28. Detect @mention in chat_api.py and fire trigger
29. Update React — remove /ai-test, handle real persona events
30. Refactor nexus-nucleus into separate Django apps
31. M4: AI Request Logging

### Context panels
32. Create ContextPanelProvider interface + registry (nexus-nucleus)
33. Implement ChatPanelProvider and FilePanelProvider
34. Add panel API endpoints to nexus-nucleus
35. Build ContextPanel frontend component
36. Wire panel button into chat header + verify end-to-end

### M7 — Output types
37. OutputType registry + built-in types (nexus-ai)
38. Cosine similarity intent classifier (nexus-ai)
39. Output type resolution + marker parsing in PydanticAIRunner
40. @output_type parsing + output_types endpoint (nexus-nucleus)
41. HtmlRenderer + TerminalRenderer + renderers index (frontend)
42. MessageItem renderer delegation + MessageInput @output_type (frontend)

### M7.1 — Sessions
49. Update milestones.txt with M7.1 and M8 design
50. Add session_timeout_minutes to CompanyAIConfig + migration
51. Create ChatSession Django model + migration
52. Add session service functions to chat/services.py
53. Update chat/api.py with full session routing logic
54. Test M7.1 end-to-end and commit

### M8 — Agents + MCP servers
55. Fix get_persona_by_mention() — select_related agent path
56. Add is_first_party + embed_output to MCPServer model + migration
57. Update chat/services.py — handle agent persona path in TriggerJob
58. Update chat/api.py — remove model-only guard for agent personas
59. Add MCPServerConfig schema + mcp_servers to PersonaConfig (nexus-ai)
60. Add MCP code path to PydanticAIRunner (nexus-ai)
61. Update parse_output_markers() — return embed_description as 3rd value
62. Inject <<<EMBED>>> instruction into html/form/terminal output type prompts
63. Scaffold nexus-mcp module structure
64. Build BestBuy MCP tools
65. Build Walmart MCP tools
66. Build ERP MCP tools with list/form output
67. Build SSH MCP tools
68. Add nexus-mcp to docker-compose.yaml
69. Split nexus-mcp into 3 separate MCP servers
70. Build AI Intelligence admin page (Models, MCPs, Agents, Personas)

### Team / membership fixes
71. Fix _format_member: use get_display_name() for humans
72. Fix list_team to exclude inactive (deleted) shadow users
73. Auto-add personas to projects on creation (and vice versa)
74. Restore @handle prefix in sidebar team list
75. Extend /invite to support @PersonaName

### Documentation
76. Create mcps/ folder structure in neuralops-staging
77. Read core/urls.py for router mount prefixes
78. Read all api.py files across nexus-nucleus apps
79. Compile use-case to API mapping table
80. Write deliverable markdown file and verify against source
81. Research slash commands and tailscale/env config for README
82. Write comprehensive README.md to repo root
83. Write ARCHITECTURE.md — module & tool rationale

### Project-scoping for AI resources
84. Fix services.py list_topics/update_topic signature mismatch
85. Verify create_channel, create_topic, mark_topic_read in services.py
86. Add Project attachment M2M to AIModel/AIAgent/MCPServer
87. Add row-visibility functions for AI resources
88. Wire list endpoints to new row-visibility functions
89. Add attach/detach endpoints for project-resource linking
90. Verify AI resource project-scoping with manage.py check + tests
91. Restrict AIAgent to single project (keep M2M, drop cross-attach)
92. Add real project FK to Persona, make list/mention project-scoped
93. MCP servers: apply same single-project pattern as Agent
94. Extend _scope_chain for AIAgent/MCPServer project reach
95. Move agent.*/mcp_server.* create+delete to PROJECT scope
96. Restructure agent/mcp create+delete endpoints to check against project
97. Fix persona.list to use row-visibility (visible_personas)
98. Update USE_CASES.md and ROLE_STORIES.md for AI resources
99. Write test cases for AI resource permission matrix

### Manual verification pass
100. Manual shell walkthrough: Projects/Channels/Topics/MCP/Agent/Model
101. Exercise remaining untested methods (Persona CRUD + deletes/patches)
102. Rename project.delete to project.archive, add channel.archive/topic.archive rights
103. Add archive_channel/archive_topic service+API functions
104. Add include_archived param to list_projects/list_channels/list_topics
105. Flush DB and recreate owner/permissions
106. Test Project methods (list/create/get/archive)
107. Test Channel methods (list/create/archive)
108. Test Topic methods (list/create/update/archive/mark_read)
109. Test AI Model methods
110. Test MCP Server methods (standalone + legacy)
111. Test Agent methods
112. Test Persona methods

### Device-auth cleanup
113. Remove poll_device_activation from authn/tasks.py
114. Remove auth_init/auth_status/DeviceAuthError from authn/services.py
115. Remove /init/ and /status/ endpoints from authn/api.py
116. Remove AuthInitResponse/AuthStatusResponse from authn/schema.py
117. Remove DeviceSession model + add drop migration
118. Move NinjaAPI + router registration from authn/urls.py to core/urls.py

### RBAC / invite fixes (#120 P0)
119. Route chat/api.py's _resolve_topic_sync through visible_channels/visible_topics
120. [P0] No invite flow ever creates a RoleAssignment — RBAC doesn't apply to real invited users
122. embed_message_async uses raw content, not directive-stripped text
123. Extract MessageDirectives parser out of send_message
124. Fix get_project() to use _reachable_project_ids fallback
125. Rename/fix send_invite() into invite_to_system()
126. Wire invite_to_project() through invite_to_system() + grant project/topic RoleAssignment
127. Fix acceptance path to grant deferred RoleAssignment
128. Move embed_message_async to fire after routing decision, not after save
129. Add pagination to list_messages endpoint
130. Move SendMessageIn validation into schema

### #131 — Push persona/model/history resolution into nexus-ai
132. Add /internal/topics/{id}/history/ endpoint (nucleus)
133. Shrink TriggerJob payload building (nucleus)
134. Add nucleus_client.py + wire AgenticManager (nexus-ai)
135. Update TriggerJob schema + PromptBuilder + AgentRunner interface (nexus-ai)
136. Write management command to test send_message/AI trigger/list_messages
137. Fix nexus-ai→nucleus DNS + add message_error handling
138. Verify test_chat_flow after docker fix
139. Confirm end-to-end AI trigger with real API key
140. Add message_error handling to frontend
142. Verify frontend build (lint/tsc/vite build)
144. Bring backend (nexus-*) stack back up alongside frontend

### #141 — Typing/thinking status indicators
141. Add typing/thinking status indicators
164. Split #141 into typing/thinking indicators + file context type
165. Wire typing/thinking indicator in useChat.ts
166. Pass real typingActors into ChatArea.tsx
167. Verify typing indicator end-to-end in browser
168. Add human typing broadcast (backend + frontend) — dedicated fixed status bar, avatar + name, multi-actor label, above the composer

### #148 — Avatars for users and personas
148. Avatars for users and personas
151. Add avatar field to User model + migration
152. Check persona shadow-user creation code
153. Build seed_avatars management command (DiceBear, ~60 human + 60 persona PNGs)
154. Write shared assign_avatar(user) helper
155. Wire assign_avatar into auth_verify() and create_persona()
156. Verify: run makemigrations/check, run seed_avatars, test via management command
157. Add User.get_avatar_url() + Django media serving
158. Wire avatar into chat message serializer + schema
159. Wire avatar into team/member list endpoints
160. Wire avatar into frontend chat rendering
161. Wire avatar into frontend members panel
162. Verify avatars render end-to-end in browser
163. Backfill avatars for existing users/personas (fixed NULL-vs-empty-string migration bug + missing nginx /media/ route along the way)

### #170 — Fat docker self-host distribution
170. Fat docker image for easy self-host distribution — `fat` Compose profile (nucleus, nucleus-celery, postgres, redis, chromadb, realtime, nginx, no frontend), three new Docker Hub images (`neuralops-nucleus`, `neuralops-nexus-ai`, `neuralops-nginx`), `install.sh`, `SELF-HOST.md`. Verified end-to-end: containers up, `migrate`/`seed_permissions`/`create_owner` run, hosted frontend "Connect" succeeds against the Tailscale Funnel URL, avatars/typing-status render correctly through the self-hosted backend. Six real bugs found and fixed during testing (wrong GitHub org, `curl\|bash` stdin/unbound-variable crash, install dir nesting, `pg_isready` false negative, nginx-fat baked with dev-network upstream names, missing Chrome Private Network Access header for Tailscale's CGNAT range) — full list in `DECISIONS.md` §20.
174. Build #170 fat docker profile + installer

---

## Known gotchas for next session

- **MCP connector only** — `node3-neuralops-staging` has no execute/git/docker access. All file edits go through the MCP `read_text_file`/`edit_file`/`write_file` tools; every docker/git/manage.py command has to be handed to the user to run and paste back.
- **Compose service name vs container_name** — DNS between containers only resolves by Compose *service* name (e.g. `nucleus`), not `container_name` (`nexus-nucleus`). This bit #131 (nexus-ai → nucleus) once already.
- **docker-compose.staging.yaml** is an override file, not standalone — always run with `-f docker-compose.yaml -f docker-compose.staging.yaml`. It holds the only full definition of the frontend service (commented out in the base file) plus a named `node_modules` volume that's required for `vite` to work at all inside the container.
- **Centrifugo runs `--client.insecure`** — no per-channel JWT authorization. Channel isolation (e.g. per-topic typing/message events) relies entirely on clients only ever subscribing to topics they legitimately have open — flagged as a real gap, not yet tracked as its own task.
- **Django migrations on nullable AddField** default *existing* rows to `NULL`, not the model's Python-level falsy default (`""` for ImageField) — bit the avatar backfill script once; any future backfill-style migration should filter `Q(field="") | Q(field__isnull=True)`.
