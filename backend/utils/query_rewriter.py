from openai import AsyncOpenAI

from config import settings


QUERY_REWRITE_PROMPT = """
你是一个检索优化助手。
用户原始问题：{query}
对话历史摘要：{context}

请将用户的问题改写为更适合检索的独立问题。如果不需要改写，直接返回原问题。
只输出问题本身，不要解释。
"""


async def rewrite_query(query: str, context_summary: str, client: AsyncOpenAI) -> str:
    try:
        response = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": QUERY_REWRITE_PROMPT.format(query=query, context=context_summary)}],
            max_tokens=200,
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        return content.strip() or query
    except Exception:
        return query

