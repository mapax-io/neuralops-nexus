from .base import (
    UUIDModel,
    TimeStampedModel,
    SoftDeleteModel,
    BaseModel,
    TenantBaseModel,
    ProjectBaseModel,
)

from .account import (
    User,
)

from .governance import (
    Company,
    CompanyAccess,
)

from .intelligence import (
    CompanyAIConfig,
    ModelConfig,
    MCPServer,
    Persona,
    AIRequestLog,
)

from .prompt import (
    PromptTemplate,
    Prompt,
)

from .workspace import (
    Project,
    Channel,
    ChatTopic,
    ChatMessage,
    ChatReadMarker,
    ChatReaction,
    ChatSession,
    ChatAttachment,
    KnowledgeBase,
    KnowledgeFile,
)

from .context import (
    ContextSource,
)

from .scheduling import (
    PersonaSchedule,
)

from .extended import (
    Invitation,
    ProjectMember,
    TopicParticipant,
    Upload,
    UploadPart,
    KnowledgeChunk,
    EmbeddingJob,
    VectorDocument,
    ProjectContext,
    TopicContext,
    AuditEvent,
    Notification,
    UserSession,
    SavedSearch,
    SearchLog,
)

# ── REMOVED EXPORTS ───────────────────────────────────────────────────────────
#   AIModel        -> renamed to ModelConfig (migration 0014)
#   AIAgent        -> deleted; Persona absorbed it (migration 0018)
#   Human          -> deleted, never populated (migration 0008)
#   AgentRun       -> deleted, unreferenced (migration 0007)
#   AgentApproval  -> deleted, unreferenced (migration 0006)
#   ModelUsageLog  -> deleted, zero writers (migration 0008)
