import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF


api_key = os.getenv("OPENAI_API_KEY")
api_base_url = os.getenv("OPENAI_API_BASE_URL") or None
model = os.getenv("OPENAI_API_MODEL", "gpt-4.1-mini")
embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL") or (
    "text-embedding-embeddinggemma-300m-qat" if api_base_url else "text-embedding-3-small"
)
embedding_dim = int(os.getenv("OPENAI_EMBEDDING_DIM") or ("768" if api_base_url else "1536"))
embedding_api_key = os.getenv("OPENAI_EMBEDDING_API_KEY", api_key)
embedding_base_url = os.getenv("OPENAI_EMBEDDING_API_BASE_URL") or api_base_url
llm_config = LLMConfig(
    api_key=api_key,
    model=model,
    small_model=model,
    base_url=api_base_url,
)

graphiti = Graphiti(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
    llm_client=OpenAIGenericClient(config=llm_config),
    embedder=OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=embedding_api_key,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            base_url=embedding_base_url,
        )
    ),
    cross_encoder=OpenAIRerankerClient(config=llm_config),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await graphiti.build_indices_and_constraints()
    yield
    await graphiti.close()


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger("uvicorn.error")
documents: dict[str, dict] = {}


@app.middleware("http")
async def log_request_start(request, call_next):
    logger.info("Request started: %s %s", request.method, request.url.path)
    return await call_next(request)


async def ingest_episode(document_id: str, text: str):
    document = documents[document_id]
    document["status"] = "processing"
    logger.info("Episode ingestion started: %s", document_id)
    try:
        await graphiti.add_episode(
            uuid=document_id,
            name=document["title"],
            episode_body=text,
            source=EpisodeType.text,
            source_description="Sample input",
            reference_time=datetime.now(timezone.utc),
            group_id="default",
        )
        document["status"] = "completed"
        logger.info("Episode ingestion completed: %s", document_id)
    except Exception:
        document["status"] = "failed"
        logger.exception("Episode ingestion failed: %s", document_id)


@app.get("/api/episodes")
async def list_episodes():
    episodes = await graphiti.retrieve_episodes(
        reference_time=datetime.now(timezone.utc),
        last_n=100,
        group_ids=["default"],
    )
    result = {
        episode.uuid: {
            "id": episode.uuid,
            "title": episode.name,
            "created_at": episode.created_at.isoformat(),
            "status": "completed",
        }
        for episode in episodes
    }
    result.update(documents)
    return sorted(result.values(), key=lambda item: item["created_at"], reverse=True)


@app.post("/api/episodes")
async def add_episode(data: dict, background_tasks: BackgroundTasks):
    document_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    title = next((line.strip() for line in data["text"].splitlines() if line.strip()), "テキスト")[:80]
    documents[document_id] = {
        "id": document_id,
        "title": title,
        "created_at": created_at,
        "status": "queued",
    }
    background_tasks.add_task(ingest_episode, document_id, data["text"])
    return documents[document_id]


@app.delete("/api/episodes/{episode_id}")
async def delete_episode(episode_id: str):
    document = documents.get(episode_id)
    if document and document["status"] in {"queued", "processing"}:
        return {"status": "processing"}
    if document and document["status"] == "failed":
        documents.pop(episode_id)
        return {"status": "deleted"}
    await graphiti.remove_episode(episode_id)
    documents.pop(episode_id, None)
    logger.info("Episode deleted: %s", episode_id)
    return {"status": "deleted"}


@app.post("/api/chat")
async def chat(data: dict):
    config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True)
    config.limit = 8
    results = await graphiti.search_(query=data["message"], config=config)

    nodes = [
        {"id": node.uuid, "name": node.name}
        for node in results.nodes
    ]
    edges = [
        {
            "id": edge.uuid,
            "source": edge.source_node_uuid,
            "target": edge.target_node_uuid,
            "name": edge.fact,
        }
        for edge in results.edges
    ]
    answer = "\n".join(edge["name"] for edge in edges) or "関連する情報は見つかりませんでした。"
    return {"answer": answer, "nodes": nodes, "edges": edges}
