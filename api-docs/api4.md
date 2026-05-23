## 1. Authentication APIs

| Method | Endpoint |
| --- | --- |
| POST | /api/v1/auth/signin |
| GET | /api/v1/auth/me |
| POST | /api/v1/auth/logout |
| POST | /api/v1/auth/refresh |
| GET | /api/v1/auth/session |

## 2. User / Human APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/users |
| GET | /api/v1/users/{user_id} |
| PATCH | /api/v1/users/{user_id} |
| DELETE | /api/v1/users/{user_id} |
| GET | /api/v1/users/{user_id}/access |
| PATCH | /api/v1/users/{user_id}/access |
| GET | /api/v1/users/{user_id}/projects |
| GET | /api/v1/users/{user_id}/channels |
| GET | /api/v1/users/{user_id}/topics |
| POST | /api/v1/users/{user_id}/activate |
| POST | /api/v1/users/{user_id}/deactivate |

## 3. Invitation APIs

| Method | Endpoint |
| --- | --- |
| POST | /api/v1/invitations |
| GET | /api/v1/invitations |
| GET | /api/v1/invitations/{invitation_id} |
| POST | /api/v1/invitations/accept |
| DELETE | /api/v1/invitations/{invitation_id} |
| POST | /api/v1/invitations/{invitation_id}/resend |

## 4. Company APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/companies |
| POST | /api/v1/companies |
| GET | /api/v1/companies/{company_id} |
| PATCH | /api/v1/companies/{company_id} |
| DELETE | /api/v1/companies/{company_id} |
| GET | /api/v1/companies/{company_id}/members |
| GET | /api/v1/companies/{company_id}/settings |
| PATCH | /api/v1/companies/{company_id}/settings |
| POST | /api/v1/companies/{company_id}/switch |

## 5. Project APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/projects |
| POST | /api/v1/projects |
| GET | /api/v1/projects/{project_id} |
| PATCH | /api/v1/projects/{project_id} |
| DELETE | /api/v1/projects/{project_id} |
| POST | /api/v1/projects/{project_id}/archive |
| POST | /api/v1/projects/{project_id}/restore |
| GET | /api/v1/projects/{project_id}/members |
| POST | /api/v1/projects/{project_id}/members |
| PATCH | /api/v1/projects/{project_id}/members/{user_id} |
| DELETE | /api/v1/projects/{project_id}/members/{user_id} |
| GET | /api/v1/projects/{project_id}/context |
| POST | /api/v1/projects/{project_id}/context |
| PATCH | /api/v1/projects/{project_id}/context/{context_id} |
| DELETE | /api/v1/projects/{project_id}/context/{context_id} |

## 6. Channel APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/projects/{project_id}/channels |
| POST | /api/v1/projects/{project_id}/channels |
| GET | /api/v1/channels/{channel_id} |
| PATCH | /api/v1/channels/{channel_id} |
| DELETE | /api/v1/channels/{channel_id} |
| POST | /api/v1/channels/{channel_id}/archive |
| POST | /api/v1/channels/{channel_id}/restore |
| GET | /api/v1/channels/{channel_id}/members |
| POST | /api/v1/channels/{channel_id}/members |
| PATCH | /api/v1/channels/{channel_id}/members/{user_id} |
| DELETE | /api/v1/channels/{channel_id}/members/{user_id} |

## 7. Topic / Chat APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/channels/{channel_id}/topics |
| POST | /api/v1/channels/{channel_id}/topics |
| GET | /api/v1/topics/{topic_id} |
| PATCH | /api/v1/topics/{topic_id} |
| DELETE | /api/v1/topics/{topic_id} |
| POST | /api/v1/topics/{topic_id}/archive |
| POST | /api/v1/topics/{topic_id}/restore |
| POST | /api/v1/topics/{topic_id}/read |
| POST | /api/v1/topics/{topic_id}/pin |
| POST | /api/v1/topics/{topic_id}/unpin |
| GET | /api/v1/topics/{topic_id}/history |

## 8. Topic Participant APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/topics/{topic_id}/participants |
| POST | /api/v1/topics/{topic_id}/participants |
| PATCH | /api/v1/topics/{topic_id}/participants/{participant_id} |
| DELETE | /api/v1/topics/{topic_id}/participants/{participant_id} |

## 9. Message APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/topics/{topic_id}/messages |
| POST | /api/v1/topics/{topic_id}/messages |
| GET | /api/v1/messages/{message_id} |
| PATCH | /api/v1/messages/{message_id} |
| DELETE | /api/v1/messages/{message_id} |
| POST | /api/v1/messages/{message_id}/truncate |
| POST | /api/v1/messages/{message_id}/retry |
| POST | /api/v1/messages/{message_id}/cancel |
| POST | /api/v1/messages/{message_id}/forms/{block_key}/submit |
| GET | /api/v1/messages/{message_id}/blocks |
| POST | /api/v1/messages/{message_id}/reactions |
| DELETE | /api/v1/messages/{message_id}/reactions/{reaction_id} |

## 10. Upload APIs

| Method | Endpoint |
| --- | --- |
| POST | /api/v1/uploads |
| GET | /api/v1/uploads/{upload_id} |
| DELETE | /api/v1/uploads/{upload_id} |
| POST | /api/v1/uploads/{upload_id}/complete |
| POST | /api/v1/uploads/multipart/start |
| POST | /api/v1/uploads/multipart/{upload_id}/part |
| POST | /api/v1/uploads/multipart/{upload_id}/finish |
| POST | /api/v1/uploads/multipart/{upload_id}/abort |

## 11. AI Model APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/models |
| POST | /api/v1/models |
| GET | /api/v1/models/{model_id} |
| PATCH | /api/v1/models/{model_id} |
| DELETE | /api/v1/models/{model_id} |
| POST | /api/v1/models/{model_id}/test |
| GET | /api/v1/models/{model_id}/health |
| GET | /api/v1/models/{model_id}/usage |

## 12. MCP Server APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/mcp-servers |
| POST | /api/v1/mcp-servers |
| GET | /api/v1/mcp-servers/{server_id} |
| PATCH | /api/v1/mcp-servers/{server_id} |
| DELETE | /api/v1/mcp-servers/{server_id} |
| POST | /api/v1/mcp-servers/{server_id}/test |
| GET | /api/v1/mcp-servers/{server_id}/tools |
| POST | /api/v1/mcp-servers/{server_id}/sync-tools |
| GET | /api/v1/mcp-servers/{server_id}/health |

## 13. AI Agent APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/agents |
| POST | /api/v1/agents |
| GET | /api/v1/agents/{agent_id} |
| PATCH | /api/v1/agents/{agent_id} |
| DELETE | /api/v1/agents/{agent_id} |
| POST | /api/v1/agents/{agent_id}/test |
| POST | /api/v1/agents/{agent_id}/run |
| POST | /api/v1/agents/{agent_id}/cancel-run |
| GET | /api/v1/agents/{agent_id}/runs |
| GET | /api/v1/agents/{agent_id}/runs/{run_id} |
| GET | /api/v1/agents/{agent_id}/runs/{run_id}/steps |
| GET | /api/v1/agents/{agent_id}/runs/{run_id}/logs |

## 14. Persona APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/personas |
| POST | /api/v1/personas |
| GET | /api/v1/personas/{persona_id} |
| PATCH | /api/v1/personas/{persona_id} |
| DELETE | /api/v1/personas/{persona_id} |
| POST | /api/v1/personas/{persona_id}/clone |

## 15. Knowledge Base APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/knowledge-bases |
| POST | /api/v1/knowledge-bases |
| GET | /api/v1/knowledge-bases/{kb_id} |
| PATCH | /api/v1/knowledge-bases/{kb_id} |
| DELETE | /api/v1/knowledge-bases/{kb_id} |
| POST | /api/v1/knowledge-bases/{kb_id}/attach |
| POST | /api/v1/knowledge-bases/{kb_id}/detach |
| POST | /api/v1/knowledge-bases/{kb_id}/reindex |
| GET | /api/v1/knowledge-bases/{kb_id}/status |
| GET | /api/v1/knowledge-bases/{kb_id}/stats |

## 16. Knowledge File APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/knowledge-bases/{kb_id}/files |
| POST | /api/v1/knowledge-bases/{kb_id}/files |
| GET | /api/v1/knowledge-files/{file_id} |
| DELETE | /api/v1/knowledge-files/{file_id} |
| POST | /api/v1/knowledge-files/{file_id}/reprocess |
| GET | /api/v1/knowledge-files/{file_id}/chunks |
| GET | /api/v1/knowledge-files/{file_id}/status |
| GET | /api/v1/knowledge-files/{file_id}/embeddings |

## 17. Search APIs

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/search |
| POST | /api/v1/knowledge/search |
| POST | /api/v1/topics/{topic_id}/search |
| POST | /api/v1/search/messages |
| POST | /api/v1/search/files |
| POST | /api/v1/search/semantic |

## 18. Embedding / Vector APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/embeddings/jobs |
| GET | /api/v1/embeddings/jobs/{job_id} |
| POST | /api/v1/embeddings/jobs/{job_id}/retry |
| DELETE | /api/v1/embeddings/vectors/{vector_id} |

## 19. Permission / RBAC APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/permissions |
| GET | /api/v1/roles |
| POST | /api/v1/roles |
| PATCH | /api/v1/roles/{role_id} |
| DELETE | /api/v1/roles/{role_id} |

## 20. Audit / Activity APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/audit/events |
| GET | /api/v1/audit/events/{event_id} |
| GET | /api/v1/activity/feed |

## 21. Notification APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/notifications |
| POST | /api/v1/notifications/read-all |
| POST | /api/v1/notifications/{notification_id}/read |

## 22. System / Health APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/health |
| GET | /api/v1/version |
| GET | /api/v1/system/status |
| GET | /api/v1/system/features |

## 23. Realtime / Streaming APIs (Missing)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/stream/topics/{topic_id} |
| GET | /api/v1/stream/messages/{message_id} |
| POST | /api/v1/stream/agents/{run_id}/cancel |

## 24. Admin / Internal APIs (Future)

| Method | Endpoint |
| --- | --- |
| GET | /api/v1/admin/users |
| GET | /api/v1/admin/companies |
| GET | /api/v1/admin/system-metrics |
| POST | /api/v1/admin/reindex-all |
| POST | /api/v1/admin/rebuild-search |

---

### Missing Models Identified

These models likely need to be added before API implementation:

* Invitation
* Upload
* UploadPart
* ProjectMember
* ChannelMember
* TopicParticipant
* Role
* Permission
* RolePermission
* AccessPolicy
* AgentRun
* AgentRunStep
* AgentToolExecution
* MessageBlock
* Notification
* AuditEvent
* EmbeddingJob
* VectorDocument
* SearchIndex
* KnowledgeChunk
* TopicContext
* ProjectContext
* ChannelContext
* UserSession

---

### Major Existing Model Adjustments Likely Needed

#### KnowledgeBase

**Remove:**

* channels M2M

**Keep:**

* projects
* topics

#### ChatMessage

**Likely add:**

* blocks
* streaming state
* token usage
* model used
* agent used
* retry_of_message
* branch_id

#### AIAgent

**Likely add:**

* enabled_tools
* enabled_mcp_servers
* memory_mode
* temperature
* max_iterations
* human_approval_required

#### Persona

**Likely add:**

* tone
* style
* behavior
* system instructions

---

### Suggested Implementation Order

1. Auth
2. Companies
3. Users + Access
4. Invitations
5. Projects
6. Channels
7. Topics
8. Messages
9. Uploads
10. Knowledge Bases
11. Search
12. AI Models
13. MCP Servers
14. Agents
15. Personas
16. Streaming
17. Audit/Notifications
18. RBAC

*Stopped here as requested.*