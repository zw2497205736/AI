import json

from openai import AsyncOpenAI

from config import settings
from prompts.rag_answer import RAG_PROMPT_TEMPLATE
from services.embedding_service import get_all_chunk_records, vector_search
from services.llm_service import create_text_response
from utils.bm25_retriever import BM25Retriever


def _build_source_item(
    content: str,
    filename: str = "",
    source_type: str = "",
    score: float | None = None,
    metadata: dict | None = None,
) -> dict:
    item = {
        "content": content,
        "filename": filename or "未命名文档",
        "source_type": source_type or "unknown",
        "metadata": metadata or {},
    }
    if score is not None:
        item["score"] = round(score, 4)
    return item


def _dedupe_queries(primary_query: str, alternate_queries: list[str] | None = None) -> list[str]:
    candidates = [primary_query, *(alternate_queries or [])]
    seen: set[str] = set()
    queries: list[str] = []
    for item in candidates:
        query = item.strip()
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries


async def hybrid_retrieve(query: str, client: AsyncOpenAI, alternate_queries: list[str] | None = None) -> list[dict]:
    all_records = get_all_chunk_records()
    all_chunks = [item["content"] for item in all_records if item.get("content")]
    content_metadata_map: dict[str, dict] = {}
    content_filename_map: dict[str, str] = {}
    records_by_doc: dict[tuple[int, str], list[dict]] = {}
    for item in all_records:
        content = str(item.get("content") or "")
        metadata = item.get("metadata") or {}
        filename = str(metadata.get("filename") or "未命名文档")
        if content and content not in content_filename_map:
            content_filename_map[content] = filename
            content_metadata_map[content] = metadata
        doc_id = int(metadata.get("doc_id") or 0)
        doc_key = (doc_id, filename)
        records_by_doc.setdefault(doc_key, []).append({"content": content, "metadata": metadata})

    for records in records_by_doc.values():
        records.sort(key=lambda item: int((item.get("metadata") or {}).get("chunk_index") or 0))

    retriever = BM25Retriever(all_chunks) if all_chunks else None

    seen: set[str] = set()
    merged: list[dict] = []
    for retrieval_query in _dedupe_queries(query, alternate_queries):
        vector_results = await vector_search(
            query=retrieval_query,
            client=client,
            top_k=settings.vector_top_k,
            min_score=settings.vector_min_score,
        )
        bm25_results = retriever.retrieve(retrieval_query, settings.bm25_top_k) if retriever else []
        for chunk in vector_results:
            if chunk not in seen:
                seen.add(chunk)
                merged.append(
                    _build_source_item(
                        chunk,
                        content_filename_map.get(chunk, ""),
                        "vector",
                        metadata=content_metadata_map.get(chunk, {}),
                    )
                )
        for chunk, score in bm25_results:
            if chunk not in seen:
                seen.add(chunk)
                merged.append(
                    _build_source_item(
                        chunk,
                        content_filename_map.get(chunk, ""),
                        "bm25",
                        float(score),
                        metadata=content_metadata_map.get(chunk, {}),
                    )
                )

    expanded: list[dict] = []
    expanded_seen: set[str] = set()
    for item in merged:
        content = str(item.get("content") or "")
        if content and content not in expanded_seen:
            expanded_seen.add(content)
            expanded.append(item)
        metadata = item.get("metadata") or {}
        filename = str(item.get("filename") or metadata.get("filename") or "未命名文档")
        doc_id = int(metadata.get("doc_id") or 0)
        chunk_index = int(metadata.get("chunk_index") or 0)
        doc_records = records_by_doc.get((doc_id, filename), [])
        if not doc_records:
            continue
        lower = chunk_index - settings.rag_neighbor_window
        upper = chunk_index + settings.rag_neighbor_window
        for neighbor in doc_records:
            neighbor_meta = neighbor.get("metadata") or {}
            neighbor_index = int(neighbor_meta.get("chunk_index") or 0)
            if neighbor_index < lower or neighbor_index > upper:
                continue
            neighbor_content = str(neighbor.get("content") or "")
            if not neighbor_content or neighbor_content in expanded_seen:
                continue
            expanded_seen.add(neighbor_content)
            expanded.append(
                _build_source_item(
                    neighbor_content,
                    filename,
                    f"{item.get('source_type', 'vector')}_neighbor",
                    metadata=neighbor_meta,
                )
            )

    return expanded[: settings.final_top_k]


async def filter_relevant_chunks(query: str, chunks: list[dict], client: AsyncOpenAI) -> list[dict]:
    if not chunks:
        return []
    try:
        candidates = []
        for index, item in enumerate(chunks[: settings.final_top_k], start=1):
            candidates.append(
                f"[{index}] 文件：{item.get('filename', '未命名文档')}\n内容：{item.get('content', '')[:1200]}"
            )
        prompt = (
            "你是知识库检索结果判定助手。\n"
            "请判断哪些候选片段与用户问题直接相关，能够作为回答依据。\n"
            "如果多个片段属于同一主题的连续上下文，应尽量一并保留，不要只保留标题摘要而丢掉实现细节。\n"
            "如果都不相关，返回空数组。\n"
            "只返回 JSON，格式为：{\"relevant_indexes\":[1,2]}。\n\n"
            f"用户问题：{query}\n\n"
            "候选片段：\n"
            + "\n\n".join(candidates)
        )
        content = await create_text_response(
            model=settings.chat_model,
            input_messages=[{"role": "user", "content": prompt}],
            max_output_tokens=120,
            temperature=0.1,
            text_format={"format": {"type": "json_object"}},
        )
        if not content.strip():
            return chunks[: settings.final_top_k]
        parsed = json.loads(content or "{}")
        indexes = parsed.get("relevant_indexes") or []
        if not isinstance(indexes, list):
            return chunks[: settings.final_top_k]
        selected: list[dict] = []
        for index in indexes:
            if isinstance(index, int) and 1 <= index <= len(chunks[: settings.final_top_k]):
                selected.append(chunks[index - 1])
        if not selected:
            return chunks[: settings.final_top_k]
        deduped: list[dict] = []
        seen: set[str] = set()
        for item in selected:
            content_key = str(item.get("content") or "")
            if content_key and content_key not in seen:
                seen.add(content_key)
                deduped.append(item)
        return deduped
    except Exception:
        return chunks


def build_rag_prompt(query: str, chunks: list[dict], memory_context: str) -> str:
    if chunks:
        context = "\n\n---\n\n".join(
            f"[{index + 1}] 来源文件：{item.get('filename', '未命名文档')}\n{item.get('content', '')}"
            for index, item in enumerate(chunks)
        )
    else:
        context = "（知识库中暂无相关内容）"
    memory_section = f"\n=== 用户个人偏好/记忆 ===\n{memory_context}\n========================\n" if memory_context else ""
    return RAG_PROMPT_TEMPLATE.format(context=context, memory_context=memory_section, query=query)
