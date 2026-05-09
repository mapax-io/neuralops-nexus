import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastembed import TextEmbedding
from .helpers import store_vectors
from .schemas import (
    ModelVerificationRequest,
    ModelVerificationResponse,
    AgentVerificationRequest,
    AgentVerificationResponse,
    EmbedMessagesRequest,
    EmbedMessagesResponse,
    LLMProviders,
)
import litellm


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_name = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

    model = TextEmbedding(model_name)

    yield {"embedder": model}

    model = None


app = FastAPI(title="NeuralOps Nucleus", lifespan=lifespan)


@app.post("/api/v1/internal/embeddings/messages", response_model=EmbedMessagesResponse)
async def embeddings_messages(payload: EmbedMessagesRequest, request: Request):
    embedder = request.state.embedder

    embeddings = list(await asyncio.to_thread(embedder.embed, payload.messages))

    vectors = [vec.tolist() for vec in embeddings]

    await store_vectors(vectors)

    return EmbedMessagesResponse()


@app.post("/api/v1/internal/models/verify", response_model=ModelVerificationResponse)
def models_verify(data: ModelVerificationRequest):
    try:
        if data.provider:
            validity = litellm.check_valid_key(
                model=f"{data.provider}/{data.model_name}", api_key=data.api_key
            )
        elif data.endpoint_url:
            validity = litellm.check_valid_key(
                model=data.model_name, api_key=data.api_key, api_base=data.endpoint_url
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Please include either a provider or an endpoint_url in the request",
            )

        if not validity:
            raise HTTPException(status_code=401, detail="Invalid API Key.")

        return ModelVerificationResponse()

    except litellm.AuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Invalid API Key: {str(e)}")

    except litellm.APIConnectionError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to the endpoint URL. Check the URL and your network: {str(e)}",
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {str(e)}")


@app.post("/api/v1/internal/agents/verify", response_model=AgentVerificationResponse)
def agents_verify(data: AgentVerificationRequest):
    return AgentVerificationResponse()


@app.get("/api/v1/internal/providers")
async def agents_verifyproviders():
    return [provider.value for provider in LLMProviders]


@app.get("/")
async def read_root():
    return {"status": "online", "message": "Nucleus AI Brain is active"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
