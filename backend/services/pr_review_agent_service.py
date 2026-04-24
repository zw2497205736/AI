import json
import logging
import re
import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from prompts.github_pr_review import REVIEW_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT_COMPACT
from prompts.github_pr_testing import UNIT_TEST_GENERATION_PROMPT, UNIT_TEST_GENERATION_PROMPT_COMPACT
from prompts.pr_review_agent_executor import PR_REVIEW_AGENT_EXECUTOR_PROMPT
from prompts.pr_review_agent_planner import PR_REVIEW_AGENT_PLANNER_PROMPT
from prompts.pr_review_agent_replanner import PR_REVIEW_AGENT_REPLANNER_PROMPT
from prompts.pr_review_agent_reporter import PR_REVIEW_AGENT_REPORTER_PROMPT
from services.github_service import build_reviewable_diff, fetch_pull_request, fetch_pull_request_files
from services.llm_service import create_text_response
from services.pr_review_tool_service import (
    build_repo_review_memory,
    build_code_search_tool_result,
    build_dependency_context_tool_result,
    build_issue_context_tool_result,
    build_related_prs_tool_result,
    build_pr_checks_tool_result,
    build_pr_commits_tool_result,
    build_pr_diff_tool_result,
    build_pr_meta_tool_result,
    extract_issue_numbers_from_text,
    infer_dependency_queries_from_diff,
    list_recent_repo_tasks,
    merge_agent_payload,
    refresh_repo_review_memory,
    search_review_knowledge,
)

logger = logging.getLogger(__name__)


PR_ERROR_RECOVERY_STRATEGY: dict[str, dict[str, str]] = {
    "github_api_error": {
        "action": "retry_then_fail",
        "description": "GitHub API 失败先短重试，仍失败则终止任务，避免基于缺失 diff 生成误导结果。",
    },
    "llm_generation_error": {
        "action": "degraded_context_retry",
        "description": "模型生成失败时缩小上下文并使用更保守提示词重试。",
    },
    "knowledge_retrieval_error": {
        "action": "skip_knowledge_continue",
        "description": "知识库失败不阻断 PR 审查，记录降级事件后继续基于 PR diff 生成。",
    },
    "empty_diff_error": {
        "action": "fail_fast",
        "description": "无可审查 diff 时直接失败，避免生成无依据审查。",
    },
    "unknown_error": {
        "action": "record_and_fail",
        "description": "未知错误记录分类和原始信息，交由任务层失败处理。",
    },
}


@dataclass
class AgentPlan:
    pr_type: str = "other"
    focus: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    knowledge_queries: list[str] = field(default_factory=list)
    code_search_queries: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    planning_note: str = ""


@dataclass
class AgentToolRecord:
    name: str
    arguments: dict[str, Any]
    output_preview: str


@dataclass
class AgentObservation:
    name: str
    kind: str
    duration_ms: int
    status: str
    detail: str = ""


@dataclass
class PRReviewAgentState:
    task_id: int
    repo_id: int
    pr_number: int
    repo_full_name: str
    pr_title: str
    pr_body: str
    diff_text: str
    changed_files: list[str]
    plan: AgentPlan = field(default_factory=AgentPlan)
    executed_steps: list[str] = field(default_factory=list)
    tool_calls: list[AgentToolRecord] = field(default_factory=list)
    knowledge_sources: list[dict[str, Any]] = field(default_factory=list)
    replans: list[dict[str, Any]] = field(default_factory=list)
    fallback_events: list[str] = field(default_factory=list)
    error_events: list[dict[str, str]] = field(default_factory=list)
    observations: list[AgentObservation] = field(default_factory=list)
    started_at_monotonic: float = field(default_factory=time.monotonic)
    repo_memory_context: str = ""
    review_content: str = ""
    test_suggestion_content: str = ""
    unit_test_generation_content: str = ""
    execution_summary: str = ""


async def _safe_markdown_completion(system_prompt: str, user_prompt: str, fallback_prompt: str | None = None) -> str:
    attempts = max(1, settings.llm_retry_attempts)
    last_exc: Exception | None = None
    prompt_candidates = [system_prompt]
    if fallback_prompt:
        prompt_candidates.append(fallback_prompt)
    for prompt_index, prompt in enumerate(prompt_candidates, start=1):
        for attempt in range(1, attempts + 1):
            try:
                content = await create_text_response(
                    model=settings.pr_agent_generation_model,
                    instructions=prompt,
                    input_messages=[{"role": "user", "content": user_prompt}],
                    max_output_tokens=1800,
                )
                normalized = content.strip()
                if normalized:
                    return normalized
                logger.warning(
                    "PR review agent markdown generation returned empty content: prompt_variant=%s attempt=%s",
                    prompt_index,
                    attempt,
                )
            except Exception as exc:
                last_exc = exc
                logger.exception("PR review agent markdown generation failed: prompt_variant=%s attempt=%s", prompt_index, attempt)
    if last_exc is not None:
        return f"生成失败：{last_exc}"
    return "生成失败：模型未返回有效内容"


def _safe_json_loads(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse JSON content, preview=%s", content[:160].replace("\n", " "))
    return {}


def _truncate(text: str, limit: int = 600) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "\n...[truncated]"


def classify_pr_agent_error(error: Exception | str) -> str:
    text = f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error)
    lowered = text.lower()
    if "no reviewable diff" in lowered or "无可用 diff" in lowered or "empty diff" in lowered:
        return "empty_diff_error"
    if any(token in lowered for token in ["github", "api.github.com", "pulls/", "pull request", "rate limit"]):
        return "github_api_error"
    if any(token in lowered for token in ["knowledge", "embedding", "chroma", "retrieve", "知识库", "向量"]):
        return "knowledge_retrieval_error"
    if any(token in lowered for token in ["llm", "model", "openai", "chat completions", "max_tokens", "模型", "生成失败"]):
        return "llm_generation_error"
    if any(token in lowered for token in ["timeout", "connection", "network", "dns"]):
        return "llm_generation_error"
    return "unknown_error"


def recovery_strategy_for(category: str) -> dict[str, str]:
    return PR_ERROR_RECOVERY_STRATEGY.get(category, PR_ERROR_RECOVERY_STRATEGY["unknown_error"])


def _record_error_event(
    state: PRReviewAgentState,
    *,
    stage: str,
    error: Exception | str,
    recovery: str | None = None,
) -> None:
    category = classify_pr_agent_error(error)
    strategy = recovery_strategy_for(category)
    state.error_events.append(
        {
            "stage": stage,
            "category": category,
            "message": _truncate(str(error), 240),
            "recovery": recovery or strategy["action"],
            "strategy": strategy["description"],
        }
    )


def _record_observation(
    state: PRReviewAgentState,
    *,
    name: str,
    kind: str,
    started_at: float,
    status: str,
    detail: str = "",
) -> None:
    state.observations.append(
        AgentObservation(
            name=name,
            kind=kind,
            duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
            status=status,
            detail=_truncate(detail, 160) if detail else "",
        )
    )


def _is_stage_success(content: str | None) -> bool:
    return bool(content and content.strip() and not content.startswith("生成失败："))


def _stage_content(state: PRReviewAgentState, stage: str) -> str:
    if stage == "review":
        return state.review_content
    if stage == "test_suggestion":
        return state.test_suggestion_content
    if stage == "unit_test":
        return state.unit_test_generation_content
    return ""


def _set_stage_content(state: PRReviewAgentState, stage: str, content: str) -> None:
    if stage == "review":
        state.review_content = content
    elif stage == "test_suggestion":
        state.test_suggestion_content = content
    elif stage == "unit_test":
        state.unit_test_generation_content = content


def _stage_completed(state: PRReviewAgentState, stage: str) -> bool:
    return _is_stage_success(_stage_content(state, stage))


def _truncate_lines(lines: list[str], limit_chars: int) -> str:
    if limit_chars <= 0:
        return ""
    parts: list[str] = []
    total = 0
    for line in lines:
        addition = len(line) + (1 if parts else 0)
        if total + addition > limit_chars:
            remaining = limit_chars - total
            if remaining > 0:
                parts.append(line[:remaining].rstrip())
            break
        parts.append(line)
        total += addition
    content = "\n".join(item for item in parts if item)
    return content.strip()


def _prioritize_changed_files(filenames: list[str], focus: list[str] | None = None) -> list[str]:
    focus_text = " ".join(focus or []).lower()
    scored: list[tuple[int, str]] = []
    for filename in filenames:
        name = filename.lower()
        score = 0
        if any(token in name for token in ["auth", "security", "permission", "admin", "payment", "order", "transaction"]):
            score += 7
        if any(token in name for token in ["service", "controller", "handler", "api", "router"]):
            score += 5
        if any(token in name for token in ["config", ".yml", ".yaml", ".json", ".toml", ".ini"]):
            score += 4
        if any(token in name for token in ["test", "spec"]):
            score -= 2
        if "安全" in focus_text and any(token in name for token in ["auth", "security", "admin"]):
            score += 3
        scored.append((score, filename))
    scored.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    return [item[1] for item in scored]


def _build_bounded_diff(diff_text: str, limit_chars: int) -> str:
    return _truncate(diff_text, limit_chars)


def _extract_diff_sections(diff_text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    chunks = [chunk.strip() for chunk in diff_text.split("\n---\n") if chunk.strip()]
    for chunk in chunks:
        lines = chunk.splitlines()
        filename = "unknown"
        for line in lines[:6]:
            if line.startswith("File: "):
                filename = line[6:].strip() or "unknown"
                break
        sections.append({"filename": filename, "content": chunk})
    return sections


def _summarize_patch_content(content: str) -> str:
    added = 0
    removed = 0
    touched_markers: list[str] = []
    patch_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
            patch_lines.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            patch_lines.append(line[1:].strip())
    for candidate in patch_lines[:20]:
        lowered = candidate.lower()
        if any(token in lowered for token in ["auth", "permission", "token", "admin"]):
            touched_markers.append("鉴权/权限")
        if any(token in lowered for token in ["status", "state", "enabled", "disabled"]):
            touched_markers.append("状态变更")
        if any(token in lowered for token in ["save(", "update", "insert", "delete", "repository", "repo"]):
            touched_markers.append("数据写入")
        if any(token in lowered for token in ["try", "catch", "except", "throw", "error"]):
            touched_markers.append("异常处理")
        if any(token in lowered for token in ["test_", "assert", "expect(", "mocker", "mock"]):
            touched_markers.append("测试断言")
    touched_markers = list(dict.fromkeys(touched_markers))
    marker_text = "、".join(touched_markers[:3]) if touched_markers else "通用逻辑"
    return f"新增 {added} 行，删除 {removed} 行；疑似涉及：{marker_text}"


def _build_file_level_summary(diff_text: str, prioritized_files: list[str], limit_chars: int) -> str:
    section_map = {item["filename"]: item["content"] for item in _extract_diff_sections(diff_text)}
    lines: list[str] = []
    for filename in prioritized_files[: settings.pr_context_changed_files_limit]:
        content = section_map.get(filename, "")
        if not content:
            lines.append(f"- {filename}：未找到 patch，需结合文件上下文确认")
            continue
        summary = _summarize_patch_content(content)
        lines.append(f"- {filename}：{summary}")
    return _truncate_lines(lines, limit_chars) or "- 无"


def _build_bounded_tool_history(state: PRReviewAgentState, limit_chars: int) -> str:
    lines = [f"- {record.name}: {record.output_preview[:200]}" for record in state.tool_calls]
    return _truncate_lines(lines, limit_chars) or "- 无"


def _build_bounded_knowledge_context(state: PRReviewAgentState, limit_chars: int) -> str:
    blocks = [
        f"[知识{index}] 来源：{item.get('filename', '未命名文档')}\n{str(item.get('content') or '')[:500]}"
        for index, item in enumerate(state.knowledge_sources[:5], start=1)
    ]
    return _truncate("\n\n".join(blocks), limit_chars) if blocks else "无"


def _rule_fallback_next_action(state: PRReviewAgentState, reason: str) -> dict[str, Any]:
    if not _has_tool_call(state, "get_pr_meta", {}):
        return {"action": "use_tool", "tool_name": "get_pr_meta", "arguments": {}, "reason": f"{reason}_missing_pr_meta"}
    if not _has_tool_call(state, "get_pr_diff", {}):
        return {"action": "use_tool", "tool_name": "get_pr_diff", "arguments": {}, "reason": f"{reason}_missing_pr_diff"}
    if state.plan.knowledge_queries:
        for query in state.plan.knowledge_queries:
            arguments = {"query": query}
            if not _has_tool_call(state, "search_review_knowledge", arguments):
                return {
                    "action": "use_tool",
                    "tool_name": "search_review_knowledge",
                    "arguments": arguments,
                    "reason": f"{reason}_missing_knowledge",
                }
    issue_numbers = extract_issue_numbers_from_text(state.pr_title, state.pr_body)
    if issue_numbers and not _has_tool_call(state, "get_issue_context", {"issue_numbers": issue_numbers}):
        return {"action": "use_tool", "tool_name": "get_issue_context", "arguments": {"issue_numbers": issue_numbers}, "reason": f"{reason}_missing_issue_context"}
    if state.plan.code_search_queries:
        for query in state.plan.code_search_queries:
            arguments = {"query": query}
            if not _has_tool_call(state, "search_repo_code", arguments):
                return {
                    "action": "use_tool",
                    "tool_name": "search_repo_code",
                    "arguments": arguments,
                    "reason": f"{reason}_missing_code_search",
                }
    if state.plan.pr_type in {"backend_api_change", "bugfix", "refactor", "config_change"} and not _has_tool_call(state, "get_pr_checks", {}):
        return {"action": "use_tool", "tool_name": "get_pr_checks", "arguments": {}, "reason": f"{reason}_missing_pr_checks"}
    if state.plan.pr_type in {"backend_api_change", "bugfix", "refactor", "mixed_change"} and not _has_tool_call(state, "get_pr_commits", {}):
        return {"action": "use_tool", "tool_name": "get_pr_commits", "arguments": {}, "reason": f"{reason}_missing_pr_commits"}
    dependency_queries = infer_dependency_queries_from_diff(state.diff_text, state.changed_files, limit=2)
    if state.plan.pr_type in {"backend_api_change", "bugfix", "refactor", "mixed_change"} and dependency_queries and not _has_tool_call(state, "get_dependency_context", {"queries": dependency_queries}):
        return {
            "action": "use_tool",
            "tool_name": "get_dependency_context",
            "arguments": {"queries": dependency_queries},
            "reason": f"{reason}_missing_dependency_context",
        }
    if state.plan.pr_type in {"backend_api_change", "bugfix", "refactor", "mixed_change"} and not _has_tool_call(state, "get_related_prs", {}):
        return {"action": "use_tool", "tool_name": "get_related_prs", "arguments": {}, "reason": f"{reason}_missing_related_prs"}
    if not _stage_completed(state, "review"):
        return {"action": "generate_stage", "stage": "review", "reason": f"{reason}_missing_review"}
    if not _stage_completed(state, "test_suggestion"):
        return {"action": "generate_stage", "stage": "test_suggestion", "reason": f"{reason}_missing_test_suggestion"}
    if not _stage_completed(state, "unit_test"):
        return {"action": "generate_stage", "stage": "unit_test", "reason": f"{reason}_missing_unit_test"}
    return {"action": "finish", "reason": f"{reason}_all_completed"}


def _build_planner_input(repo: GitHubRepository, pr_data: dict[str, Any], files: list[dict[str, Any]], diff_text: str) -> str:
    prioritized_names = _prioritize_changed_files([str(item.get("filename") or "unknown") for item in files[:20]])
    file_map = {str(item.get("filename") or "unknown"): item for item in files[:20]}
    file_lines = []
    for filename in prioritized_names:
        item = file_map.get(filename, {"filename": filename})
        file_lines.append(
            f"- {item.get('filename', 'unknown')} "
            f"(status={item.get('status', 'modified')}, +{item.get('additions', 0)}, -{item.get('deletions', 0)})"
        )
    return (
        f"仓库：{repo.repo_owner}/{repo.repo_name}\n"
        f"PR 标题：{pr_data.get('title', '')}\n"
        f"PR 描述：{pr_data.get('body') or '无'}\n"
        f"目标分支：{pr_data.get('base', {}).get('ref', '')}\n"
        f"来源分支：{pr_data.get('head', {}).get('ref', '')}\n"
        f"文件列表：\n" + ("\n".join(file_lines) or "- 无") + "\n\n"
        f"Diff 摘要：\n{_build_bounded_diff(diff_text, settings.pr_context_planner_diff_chars)}"
    )


def _build_executor_input(state: PRReviewAgentState) -> str:
    tool_history = "\n".join(
        f"- {record.name} args={record.arguments} preview={record.output_preview[:180]}"
        for record in state.tool_calls
    ) or "- 无"
    return (
        f"任务：PR#{state.pr_number} {state.pr_title}\n"
        f"仓库：{state.repo_full_name}\n"
        f"PR 类型：{state.plan.pr_type}\n"
        f"关注点：{', '.join(state.plan.focus) or '无'}\n"
        f"计划步骤：{'; '.join(state.plan.steps) or '无'}\n"
        f"已执行步骤：{'; '.join(state.executed_steps) or '无'}\n"
        f"已调用工具：\n{tool_history}\n\n"
        f"阶段完成情况：\n"
        f"- review：{'已完成' if _stage_completed(state, 'review') else '未完成'}\n"
        f"- test_suggestion：{'已完成' if _stage_completed(state, 'test_suggestion') else '未完成'}\n"
        f"- unit_test：{'已完成' if _stage_completed(state, 'unit_test') else '未完成'}"
    )


def _stage_context_goal(stage: str) -> str:
    if stage == "review":
        return "请优先判断功能正确性、边界条件、安全/权限、状态一致性和回归风险。"
    if stage == "test_suggestion":
        return "请优先围绕主路径、边界输入、异常路径、回归点和关键依赖交互设计测试。"
    if stage == "unit_test":
        return "请优先识别可单测的函数/模块、依赖 mock 点、核心断言和最小测试骨架。"
    return "请基于当前 PR 上下文完成对应阶段任务。"


def _stage_diff_budget(stage: str, degraded: bool = False) -> int:
    if degraded:
        return settings.pr_context_degraded_diff_chars
    if stage == "review":
        return settings.pr_context_stage_diff_chars
    if stage == "test_suggestion":
        return max(7000, settings.pr_context_stage_diff_chars // 2)
    if stage == "unit_test":
        return max(6000, settings.pr_context_stage_diff_chars // 2)
    return settings.pr_context_stage_diff_chars


def _stage_focus_hint(stage: str, degraded: bool = False) -> str:
    degraded_hint = "当前为降级重试：只基于文件摘要和关键 diff 输出最小可用结果，避免空泛。"
    if stage == "review":
        return (degraded_hint + " " if degraded else "") + "重点关注：真实缺陷、必须修复问题、合并风险。"
    if stage == "test_suggestion":
        return (degraded_hint + " " if degraded else "") + "重点关注：建议补充哪些测试场景、输入、预期行为。"
    if stage == "unit_test":
        return (degraded_hint + " " if degraded else "") + "重点关注：测试对象、Mock 策略、断言点、示例测试代码骨架。"
    return "重点关注：当前阶段最有价值的信息。"


def _build_stage_prompt(state: PRReviewAgentState, stage: str = "review", degraded: bool = False) -> str:
    knowledge_context = _build_bounded_knowledge_context(state, settings.pr_context_knowledge_chars)
    task_history = _build_bounded_tool_history(state, settings.pr_context_tool_history_chars)
    prioritized_files = _prioritize_changed_files(state.changed_files, state.plan.focus)
    changed_files = "\n".join(f"- {filename}" for filename in prioritized_files[: settings.pr_context_changed_files_limit]) or "- 无"
    summary_limit = settings.pr_context_degraded_summary_chars if degraded else settings.pr_context_stage_summary_chars
    file_level_summary = _build_file_level_summary(state.diff_text, prioritized_files, summary_limit)
    return (
        f"仓库：{state.repo_full_name}\n"
        f"PR 标题：{state.pr_title}\n"
        f"PR 描述：{state.pr_body or '无'}\n"
        f"PR 类型：{state.plan.pr_type}\n"
        f"当前阶段：{stage}\n"
        f"阶段目标：{_stage_context_goal(stage)}\n"
        f"阶段提示：{_stage_focus_hint(stage, degraded)}\n"
        f"审查重点：{', '.join(state.plan.focus) or '无'}\n"
        f"Planner 备注：{state.plan.planning_note or '无'}\n"
        f"变更文件：\n{changed_files}\n\n"
        f"文件级摘要：\n{file_level_summary}\n\n"
        f"工具上下文：\n{task_history}\n\n"
        f"命中的团队知识：\n{knowledge_context}\n\n"
        f"仓库历史经验：\n{state.repo_memory_context or '无'}\n\n"
        f"变更 diff：\n{_build_bounded_diff(state.diff_text, _stage_diff_budget(stage, degraded))}"
    )


def _infer_pr_type(files: list[dict[str, Any]], pr_title: str, diff_text: str) -> str:
    filenames = [str(item.get("filename") or "").lower() for item in files]
    extensions = {name.rsplit(".", 1)[-1] for name in filenames if "." in name}
    title = pr_title.lower()
    if filenames and all("test" in name or name.endswith(("test.java", "test.py", "spec.ts", "spec.js")) for name in filenames):
        return "test_only"
    if any(ext in {"md", "txt", "rst"} for ext in extensions) and len(extensions) <= 1:
        return "other"
    if any(ext in {"yml", "yaml", "json", "toml", "ini"} for ext in extensions):
        return "config_change"
    if any(ext in {"tsx", "ts", "jsx", "js", "css", "scss", "vue"} for ext in extensions):
        return "frontend_ui_change"
    if any(ext in {"java", "py", "go", "kt", "rb"} for ext in extensions):
        if "fix" in title or "bug" in title:
            return "bugfix"
        if "refactor" in title:
            return "refactor"
        return "backend_api_change"
    if "test" in title:
        return "test_only"
    if "refactor" in title:
        return "refactor"
    return "mixed_change" if len(files) > 3 else "other"


def _infer_focus(pr_type: str, files: list[dict[str, Any]]) -> list[str]:
    changed_filenames = [str(item.get("filename") or "").lower() for item in files]
    focus_map = {
        "test_only": ["算法正确性", "边界条件处理", "测试覆盖", "断言有效性"],
        "backend_api_change": ["功能逻辑", "异常处理", "接口兼容性", "回归风险"],
        "frontend_ui_change": ["交互逻辑", "状态同步", "边界展示", "回归风险"],
        "bugfix": ["修复是否闭环", "边界条件处理", "回归风险", "异常路径"],
        "refactor": ["行为一致性", "可维护性", "隐藏回归", "测试覆盖"],
        "config_change": ["配置正确性", "环境兼容性", "默认值风险", "回归风险"],
        "mixed_change": ["功能逻辑", "边界条件处理", "测试覆盖", "回归风险"],
        "other": ["功能逻辑", "代码规范", "边界条件处理", "测试覆盖"],
    }
    focus = focus_map.get(pr_type, focus_map["other"]).copy()
    if any("security" in name or "auth" in name for name in changed_filenames) and "安全性" not in focus:
        focus[0] = "安全性"
    return focus[:4]


def _infer_steps(pr_type: str) -> list[str]:
    base_steps = [
        "获取 PR 基本信息",
        "检查 PR Diff 关键变更",
        "生成 Code Review",
        "生成测试建议",
        "生成单元测试建议",
    ]
    if pr_type == "test_only":
        return [
            "获取 PR 基本信息",
            "检查测试相关 Diff",
            "生成 Code Review",
            "生成测试建议",
            "生成单元测试建议",
        ]
    return base_steps


def _infer_knowledge_queries(pr_type: str, files: list[dict[str, Any]]) -> list[str]:
    filenames = [str(item.get("filename") or "").lower() for item in files]
    queries: list[str] = []
    if pr_type in {"test_only", "backend_api_change", "bugfix"}:
        queries.append("团队单元测试规范")
    if any(name.endswith((".java", ".py", ".go", ".ts", ".js")) for name in filenames):
        queries.append("团队代码审查规范")
    return queries[:2]


def _infer_code_search_queries(pr_type: str, files: list[dict[str, Any]]) -> list[str]:
    filenames = [str(item.get("filename") or "") for item in files[:3]]
    queries: list[str] = []
    for filename in filenames:
        leaf = filename.rsplit("/", 1)[-1]
        stem = leaf.rsplit(".", 1)[0]
        if len(stem) >= 4:
            queries.append(stem)
    if pr_type in {"backend_api_change", "bugfix", "refactor"}:
        queries.append("service")
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped[:2]


async def _plan_agent(repo: GitHubRepository, pr_data: dict[str, Any], files: list[dict[str, Any]], diff_text: str) -> AgentPlan:
    rule_pr_type = _infer_pr_type(files, str(pr_data.get("title") or ""), diff_text)
    rule_focus = _infer_focus(rule_pr_type, files)
    rule_steps = _infer_steps(rule_pr_type)
    rule_knowledge_queries = _infer_knowledge_queries(rule_pr_type, files)
    rule_code_search_queries = _infer_code_search_queries(rule_pr_type, files)

    fallback_plan = AgentPlan(
        pr_type=rule_pr_type,
        focus=rule_focus,
        steps=rule_steps,
        knowledge_queries=rule_knowledge_queries,
        code_search_queries=rule_code_search_queries,
        suggested_tools=["get_pr_meta", "get_pr_diff", *(["search_review_knowledge"] if rule_knowledge_queries else [])][:4],
        planning_note="优先基于规则识别的风险点完成 PR 审查。",
    )
    issue_numbers = extract_issue_numbers_from_text(str(pr_data.get("title") or ""), str(pr_data.get("body") or ""))
    if issue_numbers:
        fallback_plan.suggested_tools.append("get_issue_context")
    if rule_pr_type in {"backend_api_change", "bugfix", "refactor", "config_change"}:
        fallback_plan.suggested_tools.append("get_pr_checks")
    if rule_pr_type in {"backend_api_change", "bugfix", "refactor", "mixed_change"}:
        fallback_plan.suggested_tools.append("get_pr_commits")
    if infer_dependency_queries_from_diff(diff_text, [str(item.get("filename") or "") for item in files[:5]], limit=2):
        fallback_plan.suggested_tools.append("get_dependency_context")
    if rule_pr_type in {"backend_api_change", "bugfix", "refactor", "mixed_change"}:
        fallback_plan.suggested_tools.append("get_related_prs")
    if rule_code_search_queries:
        fallback_plan.suggested_tools.append("search_repo_code")
    fallback_plan.suggested_tools = fallback_plan.suggested_tools[:5]

    content = await create_text_response(
        model=settings.pr_agent_control_model,
        instructions=PR_REVIEW_AGENT_PLANNER_PROMPT,
        input_messages=[{"role": "user", "content": _build_planner_input(repo, pr_data, files, diff_text)}],
        max_output_tokens=600,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    if not parsed:
        return fallback_plan
    return AgentPlan(
        pr_type=str(parsed.get("pr_type") or fallback_plan.pr_type),
        focus=[str(item) for item in parsed.get("focus") or fallback_plan.focus][:4],
        steps=[str(item) for item in parsed.get("steps") or fallback_plan.steps][:5],
        knowledge_queries=[str(item) for item in parsed.get("knowledge_queries") or fallback_plan.knowledge_queries][:3],
        code_search_queries=[str(item) for item in parsed.get("code_search_queries") or fallback_plan.code_search_queries][:2],
        suggested_tools=[str(item) for item in parsed.get("suggested_tools") or fallback_plan.suggested_tools][:4],
        planning_note=str(parsed.get("planning_note") or fallback_plan.planning_note),
    )


def _build_replanner_input(state: PRReviewAgentState, reason: str) -> str:
    return (
        f"任务：PR#{state.pr_number} {state.pr_title}\n"
        f"仓库：{state.repo_full_name}\n"
        f"当前计划：{json.dumps(asdict(state.plan), ensure_ascii=False)}\n"
        f"已执行步骤：{json.dumps(state.executed_steps, ensure_ascii=False)}\n"
        f"已调用工具：{json.dumps([asdict(item) for item in state.tool_calls], ensure_ascii=False)}\n"
        f"已命中知识条数：{len(state.knowledge_sources)}\n"
        f"阶段完成情况：review={_stage_completed(state, 'review')}, test_suggestion={_stage_completed(state, 'test_suggestion')}, unit_test={_stage_completed(state, 'unit_test')}\n"
        f"重规划原因：{reason}"
    )


async def _replan_agent(state: PRReviewAgentState, reason: str) -> None:
    content = await create_text_response(
        model=settings.pr_agent_control_model,
        instructions=PR_REVIEW_AGENT_REPLANNER_PROMPT,
        input_messages=[{"role": "user", "content": _build_replanner_input(state, reason)}],
        max_output_tokens=400,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    if not parsed:
        state.fallback_events.append(f"replan_failed:{reason}")
        return
    new_focus = [str(item) for item in parsed.get("new_focus") or []][:4]
    next_steps = [str(item) for item in parsed.get("next_steps") or []][:4]
    extra_queries = [str(item) for item in parsed.get("additional_knowledge_queries") or []][:2]
    code_search_queries = [str(item) for item in parsed.get("additional_code_search_queries") or []][:2]
    suggested_tools = [str(item) for item in parsed.get("suggested_tools") or []][:4]
    if new_focus:
        state.plan.focus = new_focus
    if next_steps:
        state.plan.steps = next_steps
    if extra_queries:
        for query in extra_queries:
            if query not in state.plan.knowledge_queries:
                state.plan.knowledge_queries.append(query)
    if code_search_queries:
        for query in code_search_queries:
            if query not in state.plan.code_search_queries:
                state.plan.code_search_queries.append(query)
    if suggested_tools:
        state.plan.suggested_tools = suggested_tools
    if parsed.get("fallback_strategy"):
        state.plan.planning_note = str(parsed.get("fallback_strategy"))
    state.replans.append(
        {
            "reason": reason,
            "replan_reason": str(parsed.get("replan_reason") or ""),
            "new_focus": new_focus,
            "next_steps": next_steps,
            "additional_knowledge_queries": extra_queries,
            "additional_code_search_queries": code_search_queries,
            "suggested_tools": suggested_tools,
        }
    )
    state.executed_steps.append(f"replan:{reason}")


async def _decide_next_action(state: PRReviewAgentState) -> dict[str, Any]:
    # Enforce a minimal rule-based workflow before model-driven control.
    preflight_action = _rule_fallback_next_action(state, "required")
    if preflight_action["action"] != "finish":
        return preflight_action

    content = await create_text_response(
        model=settings.pr_agent_control_model,
        instructions=PR_REVIEW_AGENT_EXECUTOR_PROMPT,
        input_messages=[{"role": "user", "content": _build_executor_input(state)}],
        max_output_tokens=300,
        text_format={"format": {"type": "json_object"}},
    )
    parsed = _safe_json_loads(content)
    if parsed:
        action = str(parsed.get("action") or "").strip()
        tool_name = str(parsed.get("tool_name") or "").strip() or None
        arguments = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
        stage = str(parsed.get("stage") or "").strip() or None
        if action in {"use_tool", "generate_stage", "finish"}:
            return {
                "action": action,
                "tool_name": tool_name,
                "arguments": arguments,
                "stage": stage,
                "reason": str(parsed.get("reason") or ""),
            }
        state.fallback_events.append("executor_invalid_action_schema")
    else:
        state.fallback_events.append("executor_non_json_output")
    return _rule_fallback_next_action(state, "rule_fallback")


def _has_tool_call(state: PRReviewAgentState, tool_name: str, arguments: dict[str, Any]) -> bool:
    for item in state.tool_calls:
        if item.name == tool_name and item.arguments == arguments:
            return True
    return False


async def _execute_tool(
    *,
    state: PRReviewAgentState,
    repo: GitHubRepository,
    db: AsyncSession,
    current_task_id: int,
    pr_data: dict[str, Any],
    files: list[dict[str, Any]],
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
) -> None:
    tool_name = tool_name or ""
    arguments = arguments or {}
    if not tool_name:
        pending_knowledge_queries = [
            query for query in state.plan.knowledge_queries if not _has_tool_call(state, "search_review_knowledge", {"query": query})
        ]
        if pending_knowledge_queries:
            query = pending_knowledge_queries[0]
            tool_name = "search_review_knowledge"
            arguments = {"query": query}
        elif not _has_tool_call(state, "get_pr_meta", {}):
            tool_name = "get_pr_meta"
            arguments = {}
        elif not _has_tool_call(state, "get_pr_diff", {}):
            tool_name = "get_pr_diff"
            arguments = {}
        elif not _has_tool_call(state, "list_recent_repo_tasks", {}):
            tool_name = "list_recent_repo_tasks"
            arguments = {}
        else:
            return

    if _has_tool_call(state, tool_name, arguments):
        return

    if tool_name == "get_pr_meta":
        started_at = time.monotonic()
        output = build_pr_meta_tool_result(repo, pr_data, files)
        sources: list[dict[str, Any]] = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_pr_diff":
        started_at = time.monotonic()
        output = build_pr_diff_tool_result(state.diff_text)
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_pr_checks":
        started_at = time.monotonic()
        output = await build_pr_checks_tool_result(repo, str(pr_data.get("head", {}).get("sha") or ""))
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_pr_commits":
        started_at = time.monotonic()
        output = await build_pr_commits_tool_result(repo, state.pr_number)
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_issue_context":
        started_at = time.monotonic()
        output = await build_issue_context_tool_result(
            repo,
            [int(item) for item in (arguments.get("issue_numbers") or []) if str(item).isdigit()],
        )
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "search_repo_code":
        started_at = time.monotonic()
        output = await build_code_search_tool_result(repo, str(arguments.get("query") or ""))
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_dependency_context":
        started_at = time.monotonic()
        output = await build_dependency_context_tool_result(repo, state.diff_text, state.changed_files)
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "get_related_prs":
        started_at = time.monotonic()
        output = await build_related_prs_tool_result(
            db,
            state.repo_id,
            current_task_id,
            state.pr_title,
            state.changed_files,
        )
        sources = []
        _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success")
    elif tool_name == "search_review_knowledge":
        started_at = time.monotonic()
        output, sources = await search_review_knowledge(str(arguments.get("query") or ""))
        if sources:
            state.knowledge_sources.extend(sources)
        if output.startswith("知识库检索失败"):
            state.fallback_events.append("skip_knowledge_continue:search_review_knowledge")
            _record_error_event(
                state,
                stage="tool:search_review_knowledge",
                error=output,
                recovery="skip_knowledge_continue",
            )
            _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="degraded", detail=output)
        else:
            _record_observation(state, name=tool_name, kind="tool", started_at=started_at, status="success", detail=f"sources={len(sources)}")
    else:
        started_at = time.monotonic()
        output = await list_recent_repo_tasks(db, state.repo_id, current_task_id)
        sources = []
        _record_observation(state, name="list_recent_repo_tasks", kind="tool", started_at=started_at, status="success")

    state.tool_calls.append(AgentToolRecord(name=tool_name, arguments=arguments, output_preview=_truncate(output, 280)))
    state.executed_steps.append(f"tool:{tool_name}")


async def _persist_stage_checkpoint(db: AsyncSession, task: AgentTask, state: PRReviewAgentState, stage: str) -> None:
    task.review_content = state.review_content
    task.test_suggestion_content = state.test_suggestion_content
    task.unit_test_generation_content = state.unit_test_generation_content
    task.source_payload = merge_agent_payload(
        task.source_payload,
        {
            "mode": "pr_review_agent",
            "checkpoint": {
                "last_stage": stage,
                "completed_stages": [
                    item
                    for item in ["review", "test_suggestion", "unit_test"]
                    if _stage_completed(state, item)
                ],
            },
            "executed_steps": state.executed_steps,
            "fallback_events": state.fallback_events,
            "error_events": state.error_events,
            "observability": _build_observability_summary(state),
        },
    )
    await db.commit()


async def _generate_stage(state: PRReviewAgentState, stage: str, task: AgentTask, db: AsyncSession) -> None:
    if _stage_completed(state, stage):
        state.fallback_events.append(f"resume_skip_completed_stage:{stage}")
        _record_observation(state, name=stage, kind="stage", started_at=time.monotonic(), status="skipped", detail="checkpoint_hit")
        return
    started_at = time.monotonic()
    user_prompt = _build_stage_prompt(state, stage)
    content = ""
    if stage == "review":
        content = await _safe_markdown_completion(REVIEW_SYSTEM_PROMPT, user_prompt)
        _set_stage_content(state, stage, content)
    elif stage == "test_suggestion":
        content = await _safe_markdown_completion(TEST_SYSTEM_PROMPT, user_prompt, TEST_SYSTEM_PROMPT_COMPACT)
        _set_stage_content(state, stage, content)
    elif stage == "unit_test":
        content = await _safe_markdown_completion(
            UNIT_TEST_GENERATION_PROMPT, user_prompt, UNIT_TEST_GENERATION_PROMPT_COMPACT
        )
        _set_stage_content(state, stage, content)
    if content.startswith("生成失败："):
        state.fallback_events.append(f"stage_failed:{stage}")
        _record_error_event(state, stage=stage, error=content, recovery="degraded_context_retry")
        degraded_prompt = _build_stage_prompt(state, stage, degraded=True)
        state.fallback_events.append(f"degraded_retry:{stage}")
        if stage == "review":
            content = await _safe_markdown_completion(REVIEW_SYSTEM_PROMPT, degraded_prompt)
            _set_stage_content(state, stage, content)
        elif stage == "test_suggestion":
            content = await _safe_markdown_completion(TEST_SYSTEM_PROMPT_COMPACT, degraded_prompt)
            _set_stage_content(state, stage, content)
        elif stage == "unit_test":
            content = await _safe_markdown_completion(UNIT_TEST_GENERATION_PROMPT_COMPACT, degraded_prompt)
            _set_stage_content(state, stage, content)
        if content.startswith("生成失败："):
            _record_error_event(state, stage=stage, error=content, recovery="degraded_context_retry_failed")
        else:
            state.fallback_events.append(f"degraded_retry_succeeded:{stage}")
    state.executed_steps.append(f"stage:{stage}")
    _record_observation(
        state,
        name=stage,
        kind="stage",
        started_at=started_at,
        status="failed" if content.startswith("生成失败：") else "success",
        detail="degraded_retry" if any(item.startswith(f"degraded_retry:{stage}") for item in state.fallback_events) else "",
    )
    await _persist_stage_checkpoint(db, task, state, stage)


async def _build_execution_summary(state: PRReviewAgentState) -> str:
    tool_names = ", ".join(record.name for record in state.tool_calls) or "无"
    prompt = (
        f"计划：{json.dumps(asdict(state.plan), ensure_ascii=False)}\n"
        f"工具调用：{json.dumps([asdict(item) for item in state.tool_calls], ensure_ascii=False)}\n"
        f"重规划：{json.dumps(state.replans, ensure_ascii=False)}\n"
        f"兜底事件：{json.dumps(state.fallback_events, ensure_ascii=False)}\n"
        f"阶段完成：review={_stage_completed(state, 'review')}, test_suggestion={_stage_completed(state, 'test_suggestion')}, unit_test={_stage_completed(state, 'unit_test')}"
    )
    return await _safe_markdown_completion(PR_REVIEW_AGENT_REPORTER_PROMPT, prompt)


def _build_observability_summary(state: PRReviewAgentState) -> dict[str, Any]:
    total_duration_ms = max(0, int((time.monotonic() - state.started_at_monotonic) * 1000))
    stage_durations = {
        item.name: item.duration_ms
        for item in state.observations
        if item.kind == "stage" and item.status != "skipped"
    }
    tool_durations = {
        item.name: item.duration_ms
        for item in state.observations
        if item.kind == "tool"
    }
    recovery_counts: dict[str, int] = {}
    for item in state.error_events:
        recovery = item.get("recovery", "unknown")
        recovery_counts[recovery] = recovery_counts.get(recovery, 0) + 1
    checkpoint_hits = [
        item.name
        for item in state.observations
        if item.kind == "stage" and item.status == "skipped"
    ]
    failed_categories = sorted({item.get("category", "unknown_error") for item in state.error_events})
    return {
        "total_duration_ms": total_duration_ms,
        "stage_durations_ms": stage_durations,
        "tool_durations_ms": tool_durations,
        "tool_count": len(state.tool_calls),
        "knowledge_source_count": len(state.knowledge_sources),
        "replan_count": len(state.replans),
        "fallback_count": len(state.fallback_events),
        "error_count": len(state.error_events),
        "failed_categories": failed_categories,
        "recovery_counts": recovery_counts,
        "checkpoint_hits": checkpoint_hits,
        "completed_stages": [
            stage
            for stage in ["review", "test_suggestion", "unit_test"]
            if _stage_completed(state, stage)
        ],
    }


async def _fetch_pr_context_with_recovery(
    repo: GitHubRepository,
    pr_number: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    attempts = max(1, settings.pr_recovery_github_attempts)
    fallback_events: list[str] = []
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            pr_data = await fetch_pull_request(repo, pr_number)
            files = await fetch_pull_request_files(repo, pr_number)
            if attempt > 1:
                fallback_events.append(f"github_api_retry_succeeded:attempt={attempt}")
            return pr_data, files, fallback_events
        except Exception as exc:
            last_exc = exc
            category = classify_pr_agent_error(exc)
            strategy = recovery_strategy_for(category)
            fallback_events.append(f"{strategy['action']}:{category}:attempt={attempt}")
            logger.warning(
                "PR GitHub context fetch failed: repo_id=%s pr_number=%s category=%s attempt=%s/%s",
                repo.id,
                pr_number,
                category,
                attempt,
                attempts,
                exc_info=True,
            )
            if category != "github_api_error" or attempt >= attempts:
                raise
            await asyncio.sleep(0.5 * attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("GitHub PR context fetch failed without exception")


async def run_pr_review_agent(task: AgentTask, repo: GitHubRepository, db: AsyncSession) -> PRReviewAgentState:
    pr_data, files, github_recovery_events = await _fetch_pr_context_with_recovery(repo, task.pr_number or 0)
    diff_text = build_reviewable_diff(files)
    if not diff_text.strip():
        raise ValueError("No reviewable diff content fetched from GitHub")

    state = PRReviewAgentState(
        task_id=task.id,
        repo_id=repo.id,
        pr_number=task.pr_number or 0,
        repo_full_name=f"{repo.repo_owner}/{repo.repo_name}",
        pr_title=str(pr_data.get("title") or task.title),
        pr_body=str(pr_data.get("body") or ""),
        diff_text=diff_text,
        changed_files=[str(item.get("filename") or "") for item in files if item.get("filename")],
        review_content=task.review_content if _is_stage_success(task.review_content) else "",
        test_suggestion_content=task.test_suggestion_content if _is_stage_success(task.test_suggestion_content) else "",
        unit_test_generation_content=task.unit_test_generation_content if _is_stage_success(task.unit_test_generation_content) else "",
    )
    resumed_stages = [
        stage
        for stage in ["review", "test_suggestion", "unit_test"]
        if _stage_completed(state, stage)
    ]
    if resumed_stages:
        state.fallback_events.append(f"resume_from_checkpoint:{','.join(resumed_stages)}")
    state.fallback_events.extend(github_recovery_events)
    state.plan = await _plan_agent(repo, pr_data, files, diff_text)
    state.repo_memory_context = await build_repo_review_memory(db, state.repo_id, task.id)
    logger.info(
        "PR review agent planned: task_id=%s pr_type=%s focus=%s steps=%s",
        task.id,
        state.plan.pr_type,
        state.plan.focus,
        state.plan.steps,
    )

    max_loops = 6
    last_progress_marker = ""
    stagnant_rounds = 0
    for _ in range(max_loops):
        progress_marker = json.dumps(
            {
                "steps": state.executed_steps,
                "tools": [(item.name, item.arguments) for item in state.tool_calls],
                "review": _stage_completed(state, "review"),
                "test": _stage_completed(state, "test_suggestion"),
                "unit": _stage_completed(state, "unit_test"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if progress_marker == last_progress_marker:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
            last_progress_marker = progress_marker
        if stagnant_rounds >= 2:
            await _replan_agent(state, "agent_progress_stagnant")
            stagnant_rounds = 0

        action = await _decide_next_action(state)
        action_type = str(action.get("action") or "").strip()
        logger.info("PR review agent action: task_id=%s action=%s payload=%s", task.id, action_type, action)
        if action_type == "use_tool":
            if (
                str(action.get("tool_name") or "") == "search_review_knowledge"
                and not state.plan.knowledge_queries
                and not state.knowledge_sources
            ):
                await _replan_agent(state, "knowledge_tool_requested_without_query")
            await _execute_tool(
                state=state,
                repo=repo,
                db=db,
                current_task_id=task.id,
                pr_data=pr_data,
                files=files,
                tool_name=str(action.get("tool_name") or ""),
                arguments=action.get("arguments") if isinstance(action.get("arguments"), dict) else {},
            )
            continue
        if action_type == "generate_stage":
            stage = str(action.get("stage") or "")
            if stage in {"review", "test_suggestion", "unit_test"}:
                await _generate_stage(state, stage, task, db)
                generated_content = {
                    "review": state.review_content,
                    "test_suggestion": state.test_suggestion_content,
                    "unit_test": state.unit_test_generation_content,
                }.get(stage, "")
                if generated_content.startswith("生成失败："):
                    await _replan_agent(state, f"{stage}_generation_failed")
                continue
        if action_type == "finish":
            break
        if not _stage_completed(state, "review"):
            await _generate_stage(state, "review", task, db)
        elif not _stage_completed(state, "test_suggestion"):
            await _generate_stage(state, "test_suggestion", task, db)
        elif not _stage_completed(state, "unit_test"):
            await _generate_stage(state, "unit_test", task, db)
        else:
            break

    if not _stage_completed(state, "review"):
        state.fallback_events.append("force_generate_review_after_loop")
        await _generate_stage(state, "review", task, db)
    if not _stage_completed(state, "test_suggestion"):
        state.fallback_events.append("force_generate_test_suggestion_after_loop")
        await _generate_stage(state, "test_suggestion", task, db)
    if not _stage_completed(state, "unit_test"):
        state.fallback_events.append("force_generate_unit_test_after_loop")
        await _generate_stage(state, "unit_test", task, db)

    state.execution_summary = await _build_execution_summary(state)
    observability = _build_observability_summary(state)
    task.title = state.pr_title
    task.commit_sha = pr_data.get("head", {}).get("sha") or task.commit_sha
    task.review_content = state.review_content
    task.test_suggestion_content = state.test_suggestion_content
    task.unit_test_generation_content = state.unit_test_generation_content
    state.repo_memory_context = await refresh_repo_review_memory(db, state.repo_id, task.id)
    task.source_payload = merge_agent_payload(
        task.source_payload,
        {
            "mode": "pr_review_agent",
            "plan": asdict(state.plan),
            "executed_steps": state.executed_steps,
            "tool_calls": [asdict(item) for item in state.tool_calls],
            "observations": [asdict(item) for item in state.observations],
            "replans": state.replans,
            "fallback_events": state.fallback_events,
            "error_events": state.error_events,
            "observability": observability,
            "repo_memory_context": state.repo_memory_context,
            "knowledge_sources": [
                {
                    "filename": item.get("filename", "未命名文档"),
                    "source_type": item.get("source_type", "unknown"),
                }
                for item in state.knowledge_sources[:5]
            ],
            "execution_summary": state.execution_summary,
        },
    )
    return state
