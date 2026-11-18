import os
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.search.search_config import EpisodeSearchConfig, EpisodeSearchMethod
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
            name=document["graph_name"],
            episode_body=text,
            source=EpisodeType.text,
            source_description="Sample input",
            reference_time=datetime.now(timezone.utc),
            group_id="default",
        )
        documents.pop(document_id, None)
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
    active_by_name = {document["graph_name"]: document for document in documents.values()}
    result = {
        episode.uuid: {
            "id": episode.uuid,
            "title": active_by_name.get(episode.name, {}).get("title", episode.name.partition(":")[2] or episode.name),
            "created_at": episode.created_at.isoformat(),
            "status": active_by_name.get(episode.name, {}).get("status", "completed"),
        }
        for episode in episodes
    }
    persisted_names = {episode.name for episode in episodes}
    result.update(
        {
            document_id: {key: value for key, value in document.items() if key != "graph_name"}
            for document_id, document in documents.items()
            if document["graph_name"] not in persisted_names
        }
    )
    return sorted(result.values(), key=lambda item: item["created_at"], reverse=True)


@app.post("/api/episodes")
async def add_episode(data: dict, background_tasks: BackgroundTasks):
    document_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    title = next((line.strip() for line in data["text"].splitlines() if line.strip()), "テキスト")[:80]
    graph_name = f"{document_id}:{title}"
    documents[document_id] = {
        "id": document_id,
        "title": title,
        "graph_name": graph_name,
        "created_at": created_at,
        "status": "queued",
    }
    background_tasks.add_task(ingest_episode, document_id, data["text"])
    return {key: value for key, value in documents[document_id].items() if key != "graph_name"}


@app.delete("/api/episodes/{episode_id}")
async def delete_episode(episode_id: str):
    document = documents.get(episode_id)
    if document and document["status"] in {"queued", "processing"}:
        return {"status": "processing"}
    if document and document["status"] == "failed":
        documents.pop(episode_id)
        return {"status": "deleted"}
    episode = await EpisodicNode.get_by_uuid(graphiti.driver, episode_id)
    await graphiti.remove_episode(episode_id)
    document_id = episode.name.partition(":")[0]
    documents.pop(document_id, None)
    logger.info("Episode deleted: %s", episode_id)
    return {"status": "deleted"}


@app.post("/api/chat")
async def chat(data: dict):
    config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True)
    config.limit = 8
    config.episode_config = EpisodeSearchConfig(search_methods=[EpisodeSearchMethod.bm25])
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
    question_terms = re.findall(r"[A-Za-z]+|[ぁ-んァ-ヶー一-龯]+", data["message"].casefold())
    relevant_names = [
        node.name.casefold()
        for node in results.nodes
        if node.name
        and any(
            len(term) >= 3 and any(term in query_term or query_term in term for query_term in question_terms)
            for term in re.findall(r"[A-Za-z]+|[ぁ-んァ-ヶー一-龯]+", node.name.casefold())
        )
    ]
    matched_names = relevant_names or [node.name.casefold() for node in results.nodes if node.name]
    relevant_facts = [
        edge["name"]
        for edge in edges
        if not relevant_names or any(name in edge["name"].casefold() for name in relevant_names)
    ]
    context = [f"グラフの事実: {fact}" for fact in dict.fromkeys(relevant_facts)]
    source_episodes = {}
    if matched_names:
        recent_episodes = await graphiti.retrieve_episodes(
            reference_time=datetime.now(timezone.utc),
            last_n=100,
            group_ids=["default"],
        )
        for episode in recent_episodes:
            content = episode.content.casefold()
            if any(name in content for name in matched_names):
                source_episodes.setdefault(episode.uuid, episode)
    for episode in results.episodes:
        content = episode.content.casefold()
        if not matched_names or any(name in content for name in matched_names):
            source_episodes.setdefault(episode.uuid, episode)
    context.extend(
        f"元文書: {episode.content[:3000]}"
        for episode in list(source_episodes.values())[:3]
    )
    if context:
        logger.info(
            "Chat context prepared: %d nodes, %d edges, %d source episodes",
            len(nodes),
            len(edges),
            len(source_episodes),
        )
        response = await graphiti.llm_client.client.chat.completions.create(
            model=model,
            temperature=0,
            # max_tokens=150,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "関連する元文書に直接書かれた属性を優先し、質問へ日本語で簡潔に回答してください。"
                        "『ナレッジグラフに情報がありません』と答えるのは、関連する元文書とグラフの事実の両方に"
                        "回答がない場合だけです。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"質問: {data['message']}\n\n検索コンテキスト:\n- " + "\n- ".join(context),
                },
            ],
        )
        answer = response.choices[0].message.content or "ナレッジグラフに情報がありません。"
    else:
        answer = "ナレッジグラフに情報がありません。"
    return {"answer": answer, "nodes": nodes, "edges": edges}
