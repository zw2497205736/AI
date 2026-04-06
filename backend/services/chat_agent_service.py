import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.chat_tool_service import build_agent_final_answer, execute_chat_tool, plan_chat_agent_step
from services.llm_service import create_text_response
from services.memory_service import search_long_term_memories
from services.rag_service import build_rag_prompt, filter_relevant_chunks, hybrid_retrieve
from utils.query_rewriter import rewrite_query

logger = logging.getLogger(__name__)


async def _build_non_tool_answer(
    *,
    query: str,
    user_id: str,
    short_memory,
    chat_client,
    embedding_client,
    db: AsyncSession,
) -> dict[str, Any]:
    recent_history = short_memory.get_recent_history_for_query_rewrite()
    rewritten_query = await rewrite_query(query, short_memory.get_summary_for_query_rewrite(), recent_history, chat_client)
    alternate_queries = [query] if rewritten_query.strip() != query.strip() else None
    raw_chunks = await hybrid_retrieve(rewritten_query, embedding_client, alternate_queries=alternate_queries)
    chunks = await filter_relevant_chunks(rewritten_query, raw_chunks, chat_client)
    long_term_memories = await search_long_term_memories(user_id, query, embedding_client, db)
    context_messages = short_memory.build_context_messages()
    if chunks:
        rag_prompt = build_rag_prompt(rewritten_query, chunks, "\n".join(long_term_memories))
        context_messages.append({"role": "user", "content": rag_prompt})
    else:
        if long_term_memories:
            context_messages.append(
                {
                    "role": "system",
                    "content": "以下是与当前用户相关的长期记忆，可在回答时酌情参考：\n" + "\n".join(long_term_memories),
                }
            )
        context_messages.append(
            {
                "role": "system",
                "content": "当前知识库没有命中相关资料。请直接基于你的通用能力正常回答，但不要假装引用了知识库。",
            }
        )
        context_messages.append({"role": "user", "content": query})
    full_response = await create_text_response(
        model=settings.chat_model,
        input_messages=context_messages,
        max_output_tokens=2000,
        temperature=0.7,
    )
    return {
        "response": full_response,
        "sources": chunks,
        "retrieval_hit": bool(chunks),
        "mode": "rag" if chunks else "general",
        "tool_history": [],
        "rewritten_query": rewritten_query,
        "raw_sources_count": len(raw_chunks),
    }


async def run_chat_agent(
    *,
    query: str,
    user_id: str,
    short_memory,
    chat_client,
    embedding_client,
    db: AsyncSession,
) -> dict[str, Any]:
    tool_history: list[dict[str, Any]] = []
    aggregated_sources: list[dict[str, Any]] = []
    retrieval_hit = False

    for _ in range(2):
        step = await plan_chat_agent_step(query, tool_history)
        if step.get("action") != "tool_call":
            break
        tool_result = await execute_chat_tool(
            str(step.get("tool") or ""),
            step.get("arguments") if isinstance(step.get("arguments"), dict) else {},
            query=query,
            user_id=user_id,
            db=db,
            embedding_client=embedding_client,
            chat_client=chat_client,
        )
        if tool_result is None:
            break
        tool_history.append(tool_result)
        if tool_result.get("sources"):
            aggregated_sources = tool_result["sources"]
        retrieval_hit = retrieval_hit or bool(tool_result.get("retrieval_hit"))

    if tool_history:
        response = await build_agent_final_answer(query, tool_history)
        logger.info(
            "Chat agent completed: user=%s steps=%s tools=%s retrieval_hit=%s",
            user_id,
            len(tool_history),
            [item.get("tool_name") for item in tool_history],
            retrieval_hit,
        )
        return {
            "response": response,
            "sources": aggregated_sources,
            "retrieval_hit": retrieval_hit,
            "mode": "agent",
            "tool_history": tool_history,
        }

    fallback = await _build_non_tool_answer(
        query=query,
        user_id=user_id,
        short_memory=short_memory,
        chat_client=chat_client,
        embedding_client=embedding_client,
        db=db,
    )
    logger.info(
        "Chat agent fallback: user=%s mode=%s retrieval_hit=%s raw_sources_count=%s",
        user_id,
        fallback["mode"],
        fallback["retrieval_hit"],
        fallback["raw_sources_count"],
    )
    return fallback
