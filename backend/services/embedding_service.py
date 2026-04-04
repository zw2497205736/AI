import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import AsyncOpenAI

from config import settings

DUMMY_EMBEDDING_DIM = 8


chroma_client = chromadb.PersistentClient(
    path=settings.chroma_persist_dir,
    settings=ChromaSettings(anonymized_telemetry=False),
)
collection = chroma_client.get_or_create_collection(
    name=settings.chroma_collection_name,
    metadata={"hnsw:space": "cosine"},
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
    embeddings = await embed_texts(chunks, client)
    if not embeddings:
        embeddings = [[0.0] * DUMMY_EMBEDDING_DIM for _ in chunks]
    ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "chunk_index": i, "filename": filename} for i in range(len(chunks))]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)


async def vector_search(query: str, client: AsyncOpenAI, top_k: int, min_score: float) -> list[str]:
    query_embeddings = await embed_texts([query], client)
    if not query_embeddings:
        return []
    query_embedding = query_embeddings[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "distances"],
    )
    chunks: list[str] = []
    for doc, distance in zip(results["documents"][0], results["distances"][0]):
        score = 1 - distance
        if score >= min_score:
            chunks.append(doc)
    return chunks


def get_all_chunks() -> list[str]:
    result = collection.get(include=["documents"])
    return result["documents"] or []
