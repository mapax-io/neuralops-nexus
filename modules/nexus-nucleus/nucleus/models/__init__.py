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
    PersonaDeepModel,
    PersonaFallbackModel,
    Routine,
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
    ChatSession,
)

from .context import (
    ContextSource,
)

from .scheduling import (
    InboundHook,
    PersonaSchedule,
    Runbook,
    RunbookRun,
)

from .extended import (
    Invitation,
    ProjectMember,
    TopicParticipant,
    TopicContext,
)

from .usage import (
    ModelPrice,
    UsageRecord,
)

from .runtime import (
    PausedRun,
)

from .gateway import (
    GatewayToken,
)

# ── REMOVED EXPORTS ───────────────────────────────────────────────────────────
#   RecallEntry    -> Recall removed whole (owner's ruling 2026-10-22,
#                     migration 0042); Persona.recall_enabled dropped with it
#   Deliverable    -> keep-a-reply removed whole (same ruling, migration 0042)
#   AIModel        -> renamed to ModelConfig (migration 0014)
#   AIAgent        -> deleted; Persona absorbed it (migration 0018)
#   Human          -> deleted, never populated (migration 0008)
#   AgentRun       -> deleted, unreferenced (migration 0007)
#   AgentApproval  -> deleted, unreferenced (migration 0006)
#   ModelUsageLog  -> deleted, zero writers (migration 0008)
#   KnowledgeBase, KnowledgeFile, KnowledgeChunk, EmbeddingJob, VectorDocument,
#   Upload, UploadPart, ProjectContext, AuditEvent, Notification, UserSession,
#   SavedSearch, SearchLog, ChatReaction, ChatAttachment
#                  -> deleted, zero references (Step 0, migration 0029,
#                     docs/NUCLEUS-REVAMP.md 2026-10-14)
