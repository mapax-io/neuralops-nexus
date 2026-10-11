"""
Backward-compatible re-export of legacy verification schemas.
The original schemas.py was replaced by a schemas/ package.
LLMProviders + verification models are kept here so main.py imports unchanged.
"""
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
    GROQ = "groq"
    CEREBRAS = "cerebras"
    DEEPSEEK = "deepseek"
    SAMBANOVA = "sambanova"
    FIREWORKS_AI = "fireworks_ai"
    WATSONX = "watsonx"
    DATABRICKS = "databricks"
    OLLAMA_CHAT2 = "ollama_chat2"
    DOCKER_MODEL_RUNNER = "docker_model_runner"
    CUSTOM = "custom"
    LITELLM_PROXY = "litellm_proxy"
    HOSTED_VLLM = "hosted_vllm"
    LLAMAFILE = "llamafile"
    LM_STUDIO = "lm_studio"


class ModelVerificationRequest(BaseModel):
    provider: LLMProviders | None = Field(
        default=None,
        description="An optional provider field. The endpoint url field will not be required if this is provided.",
    )
    endpoint_url: str | None = Field(
        default=None,
        description="Required in case a provider is not specified.",
    )
    api_key: str = Field(description="Auth token")
    model_name: str = Field(description="Model name")


class ModelVerificationResponse(BaseModel):
    pass


class AgentVerificationRequest(BaseModel):
    pass


class AgentVerificationResponse(BaseModel):
    pass
