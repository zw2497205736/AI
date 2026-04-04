from openai import AsyncOpenAI

from config import settings
from services.embedding_service import get_all_chunks, vector_search
from utils.bm25_retriever import BM25Retriever


RAG_PROMPT_TEMPLATE = """
你是一个团队智能助理，请严格基于参考资料回答问题。
如果参考资料不足以支持回答，请直接明确说明“不知道”或“资料不足”，不要编造。
默认使用自然语言直接回答，不要输出 JSON、字段对象、结构化键值或调试信息。
如果用户表达了偏好、习惯或语言要求，可以自然确认并记住，但回复仍然要像正常助手对话，不要展示内部提取结果。

=== 参考资料 ===
{context}
=================

{memory_context}

用户问题：{query}
"""


async def hybrid_retrieve(query: str, client: AsyncOpenAI) -> list[str]:
    vector_results = await vector_search(
        query=query,
        client=client,
        top_k=settings.vector_top_k,
        min_score=settings.vector_min_score,
    )
    all_chunks = get_all_chunks()
    bm25_results: list[str] = []
    if all_chunks:
        retriever = BM25Retriever(all_chunks)
        bm25_results = [text for text, _ in retriever.retrieve(query, settings.bm25_top_k)]

    seen: set[str] = set()
    merged: list[str] = []
    for chunk in vector_results + bm25_results:
        if chunk not in seen:
            seen.add(chunk)
            merged.append(chunk)
    return merged[: settings.final_top_k]


def build_rag_prompt(query: str, chunks: list[str], memory_context: str) -> str:
    context = "\n\n---\n\n".join(f"[{index + 1}] {chunk}" for index, chunk in enumerate(chunks)) if chunks else "（知识库中暂无相关内容）"
    memory_section = f"\n=== 用户个人偏好/记忆 ===\n{memory_context}\n========================\n" if memory_context else ""
    return RAG_PROMPT_TEMPLATE.format(context=context, memory_context=memory_section, query=query)
