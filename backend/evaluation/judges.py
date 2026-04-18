from __future__ import annotations

import json
from typing import Any

from .schemas import EndToEndMetrics, GenerationMetrics, RetrievedChunk


GENERATION_JUDGE_PROMPT = """你是 RAG 回答质量评估器。
你需要基于用户问题、检索上下文、模型答案，对回答质量打分。

输出 JSON：
{
  "judge_score": 1-5,
  "judge_label": "excellent|good|partial|poor|bad",
  "judge_reason": "简洁说明",
  "faithfulness": 0-1,
  "answer_relevance": 0-1,
  "context_relevance": 0-1
}

打分原则：
- faithfulness：答案是否忠于上下文，是否有幻觉
- answer_relevance：答案是否直接回答了问题
- context_relevance：检索上下文是否真正支撑回答
只返回 JSON，不要输出额外文本。
"""


CORRECTNESS_JUDGE_PROMPT = """你是端到端问答正确性评估器。
请基于问题、标准答案和模型答案，判断模型答案的正确性和完整性。

输出 JSON：
{
  "correctness_score": 1-5,
  "correctness_label": "excellent|good|partial|poor|bad",
  "correctness_reason": "简洁说明"
}

只返回 JSON，不要输出额外文本。
"""


def _safe_json_loads(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_context_text(contexts: list[RetrievedChunk]) -> str:
    lines: list[str] = []
    for index, chunk in enumerate(contexts[:5], start=1):
        lines.append(f"[{index}] 文件：{chunk.filename}\n{chunk.content[:800]}")
    return "\n\n".join(lines) or "无"


async def judge_generation(*, model: str, question: str, answer: str, contexts: list[RetrievedChunk]) -> GenerationMetrics:
    from services.llm_service import create_text_response

    content = await create_text_response(
        model=model,
        instructions=GENERATION_JUDGE_PROMPT,
        input_messages=[
            {
                "role": "user",
                "content": (
                    f"问题：{question}\n\n"
                    f"检索上下文：\n{_build_context_text(contexts)}\n\n"
                    f"模型答案：\n{answer}"
                ),
            }
        ],
        max_output_tokens=300,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    return GenerationMetrics(
        faithfulness=_to_optional_float(parsed.get("faithfulness")),
        answer_relevance=_to_optional_float(parsed.get("answer_relevance")),
        context_relevance=_to_optional_float(parsed.get("context_relevance")),
        judge_score=_to_optional_float(parsed.get("judge_score")),
        judge_label=str(parsed.get("judge_label") or "") or None,
        judge_reason=str(parsed.get("judge_reason") or "") or None,
    )


async def judge_correctness(*, model: str, question: str, answer: str, gold_answer: str) -> EndToEndMetrics:
    from services.llm_service import create_text_response

    content = await create_text_response(
        model=model,
        instructions=CORRECTNESS_JUDGE_PROMPT,
        input_messages=[
            {
                "role": "user",
                "content": f"问题：{question}\n\n标准答案：\n{gold_answer}\n\n模型答案：\n{answer}",
            }
        ],
        max_output_tokens=220,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    return EndToEndMetrics(
        correctness_score=_to_optional_float(parsed.get("correctness_score")),
        correctness_label=str(parsed.get("correctness_label") or "") or None,
        correctness_reason=str(parsed.get("correctness_reason") or "") or None,
    )


def _to_optional_float(value: Any):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
