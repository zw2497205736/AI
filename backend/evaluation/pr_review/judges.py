from __future__ import annotations

import json
from typing import Any

from .schemas import StageJudgeMetrics


REVIEW_STAGE_JUDGE_PROMPT = """你是 GitHub PR Code Review 质量评估器。
请基于 PR 标题、标准答案和 Agent 输出，判断当前 review 输出质量。

输出 JSON：
{
  "judge_score": 1-5,
  "judge_label": "excellent|good|partial|poor|bad",
  "judge_reason": "简洁说明"
}

评分重点：
- 是否抓到了真实工程风险
- 是否漏掉关键问题
- 是否有证据、是否足够具体
- 是否存在明显空话或编造问题

只返回 JSON，不要输出额外文本。
"""


TEST_STAGE_JUDGE_PROMPT = """你是测试建议质量评估器。
请基于 PR 标题、标准测试重点和 Agent 输出，判断测试建议质量。

输出 JSON：
{
  "judge_score": 1-5,
  "judge_label": "excellent|good|partial|poor|bad",
  "judge_reason": "简洁说明"
}

评分重点：
- 是否覆盖关键测试重点
- 是否具有可执行性
- 是否识别边界、异常、回归风险
- 是否存在明显空泛建议

只返回 JSON，不要输出额外文本。
"""


UNIT_TEST_STAGE_JUDGE_PROMPT = """你是单元测试建议质量评估器。
请基于 PR 标题、标准测试目标和 Agent 输出，判断单测建议质量。

输出 JSON：
{
  "judge_score": 1-5,
  "judge_label": "excellent|good|partial|poor|bad",
  "judge_reason": "简洁说明"
}

评分重点：
- 是否贴近目标函数/模块
- 是否指出 mock、断言和测试骨架
- 是否具有可落地性
- 是否存在明显空泛表述

只返回 JSON，不要输出额外文本。
"""


def _safe_json_loads(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


async def judge_review_stage(*, model: str, pr_title: str, ground_truth: dict[str, Any], output: str) -> StageJudgeMetrics:
    return await _judge_stage(
        model=model,
        instructions=REVIEW_STAGE_JUDGE_PROMPT,
        user_content=(
            f"PR 标题：{pr_title}\n\n"
            f"标准答案：\n{json.dumps(ground_truth, ensure_ascii=False)}\n\n"
            f"Agent 输出：\n{output}"
        ),
    )


async def judge_test_stage(*, model: str, pr_title: str, ground_truth: dict[str, Any], output: str) -> StageJudgeMetrics:
    return await _judge_stage(
        model=model,
        instructions=TEST_STAGE_JUDGE_PROMPT,
        user_content=(
            f"PR 标题：{pr_title}\n\n"
            f"标准测试重点：\n{json.dumps(ground_truth, ensure_ascii=False)}\n\n"
            f"Agent 输出：\n{output}"
        ),
    )


async def judge_unit_test_stage(*, model: str, pr_title: str, ground_truth: dict[str, Any], output: str) -> StageJudgeMetrics:
    return await _judge_stage(
        model=model,
        instructions=UNIT_TEST_STAGE_JUDGE_PROMPT,
        user_content=(
            f"PR 标题：{pr_title}\n\n"
            f"标准测试目标：\n{json.dumps(ground_truth, ensure_ascii=False)}\n\n"
            f"Agent 输出：\n{output}"
        ),
    )


async def _judge_stage(*, model: str, instructions: str, user_content: str) -> StageJudgeMetrics:
    from services.llm_service import create_text_response

    content = await create_text_response(
        model=model,
        instructions=instructions,
        input_messages=[{"role": "user", "content": user_content}],
        max_output_tokens=240,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    return StageJudgeMetrics(
        judge_score=_to_optional_float(parsed.get("judge_score")),
        judge_label=str(parsed.get("judge_label") or "") or None,
        judge_reason=str(parsed.get("judge_reason") or "") or None,
    )


def average_stage_judges(items: list[StageJudgeMetrics]) -> StageJudgeMetrics:
    actual_scores = [item.judge_score for item in items if item.judge_score is not None]
    return StageJudgeMetrics(
        judge_score=(sum(actual_scores) / len(actual_scores)) if actual_scores else None,
        judge_label=None,
        judge_reason=None,
    )


def _to_optional_float(value: Any):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
