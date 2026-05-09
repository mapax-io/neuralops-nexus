from pydantic import BaseModel, Field
from enum import Enum


class LLMProviders(str, Enum):
    OPENAI = "openai"
    CHATGPT = "chatgpt"
    OPENAI_LIKE = "openai_like"
    JINA_AI = "jina_ai"
    XAI = "xai"
    ZAI = "zai"
    CUSTOM_OPENAI = "custom_openai"
    TEXT_COMPLETION_OPENAI = "text-completion-openai"
    COHERE = "cohere"
    COHERE_CHAT = "cohere_chat"
    CLARIFAI = "clarifai"
    ANTHROPIC = "anthropic"
    ANTHROPIC_TEXT = "anthropic_text"
    BYTEZ = "bytez"
    REPLICATE = "replicate"
    RUNWAYML = "runwayml"
    AWS_POLLY = "aws_polly"
    HUGGINGFACE = "huggingface"
    TOGETHER_AI = "together_ai"
    OPENROUTER = "openrouter"
    DATAROBOT = "datarobot"
    VERTEX_AI = "vertex_ai"
    VERTEX_AI_BETA = "vertex_ai_beta"
    GEMINI = "gemini"
    AI21 = "ai21"
    BASETEN = "baseten"
    BLACK_FOREST_LABS = "black_forest_labs"
    AZURE = "azure"
    AZURE_TEXT = "azure_text"
    AZURE_AI = "azure_ai"
    SAGEMAKER = "sagemaker"
    SAGEMAKER_CHAT = "sagemaker_chat"
    SAGEMAKER_NOVA = "sagemaker_nova"
    BEDROCK = "bedrock"
    VLLM = "vllm"
    NLP_CLOUD = "nlp_cloud"
    PETALS = "petals"
    OOBABOOGA = "oobabooga"
    OLLAMA = "ollama"
    OLLAMA_CHAT = "ollama_chat"
    DEEPINFRA = "deepinfra"
    PERPLEXITY = "perplexity"
    MISTRAL = "mistral"
    MILVUS = "milvus"
    GROQ = "groq"
    A2A = "a2a"
    GIGACHAT = "gigachat"
    NVIDIA_NIM = "nvidia_nim"
    CEREBRAS = "cerebras"
    AI21_CHAT = "ai21_chat"
    VOLCENGINE = "volcengine"
    CODESTRAL = "codestral"
    TEXT_COMPLETION_CODESTRAL = "text-completion-codestral"
    DASHSCOPE = "dashscope"
    MOONSHOT = "moonshot"
    PUBLICAI = "publicai"
    V0 = "v0"
    MORPH = "morph"
    LAMBDA_AI = "lambda_ai"
    DEEPSEEK = "deepseek"
    SAMBANOVA = "sambanova"
    MARITALK = "maritalk"
    VOYAGE = "voyage"
    CLOUDFLARE = "cloudflare"
    XINFERENCE = "xinference"
    FIREWORKS_AI = "fireworks_ai"
    FRIENDLIAI = "friendliai"
    FEATHERLESS_AI = "featherless_ai"
    WATSONX = "watsonx"
    WATSONX_TEXT = "watsonx_text"
    TRITON = "triton"
    PREDIBASE = "predibase"
    DATABRICKS = "databricks"
    EMPOWER = "empower"
    GITHUB = "github"
    RAGFLOW = "ragflow"
    COMPACTIFAI = "compactifai"
    DOCKER_MODEL_RUNNER = "docker_model_runner"
    CUSTOM = "custom"
    LITELLM_PROXY = "litellm_proxy"
    HOSTED_VLLM = "hosted_vllm"
    LLAMAFILE = "llamafile"
    LM_STUDIO = "lm_studio"
    GALADRIEL = "galadriel"
    NEBIUS = "nebius"
    INFINITY = "infinity"
    DEEPGRAM = "deepgram"
    ELEVENLABS = "elevenlabs"
    NOVITA = "novita"
    AIOHTTP_OPENAI = "aiohttp_openai"
    LANGFUSE = "langfuse"
    HUMANLOOP = "humanloop"
    TOPAZ = "topaz"
    SAP_GENERATIVE_AI_HUB = "sap"
    ASSEMBLYAI = "assemblyai"
    CHARITY_ENGINE = "charity_engine"
    GITHUB_COPILOT = "github_copilot"
    SNOWFLAKE = "snowflake"
    GRADIENT_AI = "gradient_ai"
    LLAMA = "meta_llama"
    NSCALE = "nscale"
    PG_VECTOR = "pg_vector"
    S3_VECTORS = "s3_vectors"
    HELICONE = "helicone"
    HYPERBOLIC = "hyperbolic"
    RECRAFT = "recraft"
    FAL_AI = "fal_ai"
    STABILITY = "stability"
    HEROKU = "heroku"
    AIML = "aiml"
    COMETAPI = "cometapi"
    OCI = "oci"
    AUTO_ROUTER = "auto_router"
    VERCEL_AI_GATEWAY = "vercel_ai_gateway"
    DOTPROMPT = "dotprompt"
    MANUS = "manus"
    WANDB = "wandb"
    OVHCLOUD = "ovhcloud"
    LEMONADE = "lemonade"
    AMAZON_NOVA = "amazon_nova"
    A2A_AGENT = "a2a_agent"
    LANGGRAPH = "langgraph"
    MINIMAX = "minimax"
    SYNTHETIC = "synthetic"
    APERTIS = "apertis"
    NANOGPT = "nano-gpt"
    POE = "poe"
    CHUTES = "chutes"
    XIAOMI_MIMO = "xiaomi_mimo"
    LITELLM_AGENT = "litellm_agent"
    CURSOR = "cursor"
    BEDROCK_MANTLE = "bedrock_mantle"


class ModelVerificationRequest(BaseModel):
    provider: LLMProviders | None = Field(
        default=None,
        description="An optional provider field. The endpoint url field will not be required if this is provided, for a list of supported providers please see GET v1/internal/providers/",
    )

    endpoint_url: str | None = Field(
        default=None, description="Required in case a provider is not specified."
    )

    api_key: str = Field(description="Auth token")

    model_name: str = Field(description="Model name")


class ModelVerificationResponse(BaseModel):
    pass


class AgentVerificationRequest(BaseModel):
    pass


class AgentVerificationResponse(BaseModel):
    pass


class EmbedMessagesRequest(BaseModel):
    messages: list[str] = Field(description="A list of messages to embed")


class EmbedMessagesResponse(BaseModel):
    pass
