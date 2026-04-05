from config import settings
from prompts.query import QUERY_REWRITE_PROMPT
from services.llm_service import create_text_response


async def rewrite_query(query: str, context_summary: str, client=None) -> str:
    try:
        content = await create_text_response(
            model=settings.chat_model,
            input_messages=[{"role": "user", "content": QUERY_REWRITE_PROMPT.format(query=query, context=context_summary)}],
            max_output_tokens=200,
            temperature=0.2,
        )
        return content.strip() or query
    except Exception:
        return query
