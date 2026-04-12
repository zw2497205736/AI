import asyncio

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import AsyncOpenAI

from config import settings
from services.llm_service import get_embedding_sync_client

try:
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings

    HAS_LANGCHAIN = True
except ImportError:
    Chroma = None
    Document = None
    Embeddings = object
    HAS_LANGCHAIN = False

DUMMY_EMBEDDING_DIM = 8


chroma_client = chromadb.PersistentClient(
    path=settings.chroma_persist_dir,
    settings=ChromaSettings(anonymized_telemetry=False),
)
collection = chroma_client.get_or_create_collection(
    name=settings.chroma_collection_name,
    metadata={"hnsw:space": "cosine"},
)


class CompatibleOpenAIEmbeddings(Embeddings):
    def __init__(self):
        self.client = get_embedding_sync_client()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        batch_size = max(1, settings.embedding_batch_size)
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = self.client.embeddings.create(input=batch, model=settings.embedding_model)
            embeddings.extend(item.embedding for item in response.data)
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        response = self.client.embeddings.create(input=[text], model=settings.embedding_model)
        return response.data[0].embedding


langchain_vector_store = (
    Chroma(
        client=chroma_client,
        collection_name=settings.chroma_collection_name,
        embedding_function=CompatibleOpenAIEmbeddings(),
    )
    if HAS_LANGCHAIN
    else None
)


async def embed_texts(texts: list[str], client: AsyncOpenAI) -> list[list[float]]:
    if not texts:
        return []
    try:
        embeddings: list[list[float]] = []
        batch_size = max(1, settings.embedding_batch_size)
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = await client.embeddings.create(input=batch, model=settings.embedding_model)
            embeddings.extend(item.embedding for item in response.data)
        return embeddings
    except Exception:
        return []


async def add_chunks_to_store(doc_id: int, filename: str, chunks: list[str], client: AsyncOpenAI):
    ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
    if HAS_LANGCHAIN and langchain_vector_store is not None:
        documents = [
            Document(
                page_content=chunk,
                metadata={"doc_id": doc_id, "chunk_index": i, "filename": filename},
                id=ids[i],
            )
            for i, chunk in enumerate(chunks)
        ]
        try:
            await asyncio.to_thread(langchain_vector_store.add_documents, documents, ids)
            return
        except Exception:
            pass
    embeddings = await embed_texts(chunks, client)
    if not embeddings:
        embeddings = [[0.0] * DUMMY_EMBEDDING_DIM for _ in chunks]
    metadatas = [{"doc_id": doc_id, "chunk_index": i, "filename": filename} for i in range(len(chunks))]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)


async def vector_search(query: str, client: AsyncOpenAI, top_k: int, min_score: float) -> list[str]:
    try:
        collection_count = int(collection.count())
    except Exception:
        collection_count = 0
    safe_top_k = max(0, min(top_k, collection_count)) if collection_count else top_k
    if safe_top_k <= 0:
        return []

    if HAS_LANGCHAIN and langchain_vector_store is not None:
        try:
            results = await asyncio.to_thread(langchain_vector_store.similarity_search_with_score, query, safe_top_k)
            chunks: list[str] = []
            max_distance = 1 - min_score
            for doc, distance in results:
                if distance <= max_distance:
                    chunks.append(doc.page_content)
            return chunks
        except Exception:
            pass
    query_embeddings = await embed_texts([query], client)
    if not query_embeddings:
        return []
    query_embedding = query_embeddings[0]
    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=safe_top_k,
            include=["documents", "distances"],
        )
    except Exception:
        return []
    chunks: list[str] = []
    for doc, distance in zip(results["documents"][0], results["distances"][0]):
        score = 1 - distance
        if score >= min_score:
            chunks.append(doc)
    return chunks


def get_all_chunks() -> list[str]:
    result = collection.get(include=["documents"])
    return result["documents"] or []


def get_all_chunk_records() -> list[dict]:
    result = collection.get(include=["documents", "metadatas"])
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    records: list[dict] = []
    for index, document in enumerate(documents):
        records.append(
            {
                "content": document,
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
        )
    return records
