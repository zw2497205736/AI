from config import settings
from prompts.manual_code_review import CODE_REVIEW_SYSTEM_PROMPT
from services.llm_service import stream_text_response


async def stream_code_review(code_diff: str, language: str, client=None):
    user_message = f"请对以下{'代码变更（diff）' if language == 'diff' else f'{language}代码'}进行 Code Review：\n\n```{language}\n{code_diff}\n```"
    async for chunk in stream_text_response(
        model=settings.chat_model,
        instructions=CODE_REVIEW_SYSTEM_PROMPT,
        input_messages=[{"role": "user", "content": user_message}],
        temperature=0.3,
        max_output_tokens=3000,
    ):
        yield chunk
