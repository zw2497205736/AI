try:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    HAS_LANGCHAIN = True
except ImportError:
    StrOutputParser = None
    ChatPromptTemplate = None
    RunnableLambda = None
    HAS_LANGCHAIN = False

from config import settings
from prompts.rag_query_rewrite import QUERY_REWRITE_PROMPT
from services.llm_service import create_text_response


def _normalize_role(role: str) -> str:
    if role == "human":
        return "user"
    if role == "ai":
        return "assistant"
    if role in {"system", "user", "assistant"}:
        return role
    return "user"


def _format_recent_history(recent_messages: list[dict] | None) -> str:
    if not recent_messages:
        return "（无最近对话）"
    lines: list[str] = []
    for item in recent_messages:
        if not isinstance(item, dict):
            continue
        role = "用户" if str(item.get("role", "")).strip() == "user" else "AI"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"{role}：{content}")
    return "\n".join(lines) if lines else "（无最近对话）"


async def _invoke_rewrite_model(prompt_value) -> str:
    messages: list[dict[str, str]] = []
    for message in prompt_value.to_messages():
        messages.append(
            {
                "role": _normalize_role(getattr(message, "type", "user")),
                "content": str(message.content),
            }
        )
    return await create_text_response(
        model=settings.chat_model,
        input_messages=messages,
        max_output_tokens=200,
        temperature=0.2,
    )


async def rewrite_query(query: str, context_summary: str, recent_messages: list[dict] | None = None, client=None) -> str:
    try:
        if not HAS_LANGCHAIN:
            content = await create_text_response(
                model=settings.chat_model,
                input_messages=[
                    {
                        "role": "user",
                        "content": QUERY_REWRITE_PROMPT.format(
                            query=query,
                            context=context_summary,
                            recent_history=_format_recent_history(recent_messages),
                        ),
                    }
                ],
                max_output_tokens=200,
                temperature=0.2,
            )
            rewritten = content.strip()
            return rewritten or query
        chain = (
            ChatPromptTemplate.from_template(QUERY_REWRITE_PROMPT)
            | RunnableLambda(_invoke_rewrite_model)
            | StrOutputParser()
        )
        content = await chain.ainvoke(
            {
                "query": query,
                "context": context_summary,
                "recent_history": _format_recent_history(recent_messages),
            }
        )
        rewritten = content.strip()
        return rewritten or query
    except Exception:
        return query
