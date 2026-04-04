from openai import AsyncOpenAI

from config import settings


CODE_REVIEW_SYSTEM_PROMPT = """
你是一名资深代码评审专家。
请严格按以下结构输出 Markdown：

### 评审概览
- 变更意图：
- 整体评分：

### 🔴 Critical 问题（必须修复）
若无则写“无”

### 🟡 Warning 问题（建议修复）
若无则写“无”

### 🔵 Info 优化建议
若无则写“无”

### 总结
"""


async def stream_code_review(code_diff: str, language: str, client: AsyncOpenAI):
    user_message = f"请对以下{'代码变更（diff）' if language == 'diff' else f'{language}代码'}进行 Code Review：\n\n```{language}\n{code_diff}\n```"
    stream = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": CODE_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        stream=True,
        temperature=0.3,
        max_tokens=3000,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content

