import json
import logging
import re
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
    build_pr_diff_tool_result,
    build_pr_meta_tool_result,
    list_recent_repo_tasks,
    merge_agent_payload,
    search_review_knowledge,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentPlan:
    pr_type: str = "other"
    focus: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    knowledge_queries: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    planning_note: str = ""


@dataclass
class AgentToolRecord:
    name: str
    arguments: dict[str, Any]
    output_preview: str


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
                    model=settings.chat_model,
                    instructions=prompt,
                    input_messages=[{"role": "user", "content": user_prompt}],
                    max_output_tokens=1800,
                )
                return content.strip() or "暂无结果"
            except Exception as exc:
                last_exc = exc
                logger.exception("PR review agent markdown generation failed: prompt_variant=%s attempt=%s", prompt_index, attempt)
    return f"生成失败：{last_exc}"


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


def _build_planner_input(repo: GitHubRepository, pr_data: dict[str, Any], files: list[dict[str, Any]], diff_text: str) -> str:
    file_lines = []
    for item in files[:20]:
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
        f"Diff 摘要：\n{_truncate(diff_text, 5000)}"
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
        f"- review：{'已完成' if state.review_content else '未完成'}\n"
        f"- test_suggestion：{'已完成' if state.test_suggestion_content else '未完成'}\n"
        f"- unit_test：{'已完成' if state.unit_test_generation_content else '未完成'}"
    )


def _build_stage_prompt(state: PRReviewAgentState) -> str:
    knowledge_context = "\n\n".join(
        f"[知识{index}] 来源：{item.get('filename', '未命名文档')}\n{str(item.get('content') or '')[:500]}"
        for index, item in enumerate(state.knowledge_sources[:5], start=1)
    ) or "无"
    task_history = "\n".join(
        f"- {record.name}: {record.output_preview[:200]}"
        for record in state.tool_calls
    ) or "- 无"
    changed_files = "\n".join(f"- {filename}" for filename in state.changed_files[:20]) or "- 无"
    return (
        f"仓库：{state.repo_full_name}\n"
        f"PR 标题：{state.pr_title}\n"
        f"PR 描述：{state.pr_body or '无'}\n"
        f"PR 类型：{state.plan.pr_type}\n"
        f"审查重点：{', '.join(state.plan.focus) or '无'}\n"
        f"Planner 备注：{state.plan.planning_note or '无'}\n"
        f"变更文件：\n{changed_files}\n\n"
        f"工具上下文：\n{task_history}\n\n"
        f"命中的团队知识：\n{knowledge_context}\n\n"
        f"变更 diff：\n{state.diff_text}"
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


async def _plan_agent(repo: GitHubRepository, pr_data: dict[str, Any], files: list[dict[str, Any]], diff_text: str) -> AgentPlan:
    rule_pr_type = _infer_pr_type(files, str(pr_data.get("title") or ""), diff_text)
    rule_focus = _infer_focus(rule_pr_type, files)
    rule_steps = _infer_steps(rule_pr_type)
    rule_knowledge_queries = _infer_knowledge_queries(rule_pr_type, files)

    fallback_plan = AgentPlan(
        pr_type=rule_pr_type,
        focus=rule_focus,
        steps=rule_steps,
        knowledge_queries=rule_knowledge_queries,
        suggested_tools=["get_pr_meta", "get_pr_diff", *(["search_review_knowledge"] if rule_knowledge_queries else [])][:4],
        planning_note="优先基于规则识别的风险点完成 PR 审查。",
    )

    content = await create_text_response(
        model=settings.chat_model,
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
        f"阶段完成情况：review={bool(state.review_content)}, test_suggestion={bool(state.test_suggestion_content)}, unit_test={bool(state.unit_test_generation_content)}\n"
        f"重规划原因：{reason}"
    )


async def _replan_agent(state: PRReviewAgentState, reason: str) -> None:
    content = await create_text_response(
        model=settings.chat_model,
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
    suggested_tools = [str(item) for item in parsed.get("suggested_tools") or []][:4]
    if new_focus:
        state.plan.focus = new_focus
    if next_steps:
        state.plan.steps = next_steps
    if extra_queries:
        for query in extra_queries:
            if query not in state.plan.knowledge_queries:
                state.plan.knowledge_queries.append(query)
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
            "suggested_tools": suggested_tools,
        }
    )
    state.executed_steps.append(f"replan:{reason}")


async def _decide_next_action(state: PRReviewAgentState) -> dict[str, Any]:
    # Enforce a minimal tool-use policy before generation so the module
    # behaves like an actual review agent rather than a pure prompt chain.
    if not _has_tool_call(state, "get_pr_meta", {}):
        return {"action": "use_tool", "tool_name": "get_pr_meta", "arguments": {}, "reason": "required_context_bootstrap"}
    if not _has_tool_call(state, "get_pr_diff", {}):
        return {"action": "use_tool", "tool_name": "get_pr_diff", "arguments": {}, "reason": "required_diff_context"}
    if state.plan.knowledge_queries:
        for query in state.plan.knowledge_queries:
            arguments = {"query": query}
            if not _has_tool_call(state, "search_review_knowledge", arguments):
                return {
                    "action": "use_tool",
                    "tool_name": "search_review_knowledge",
                    "arguments": arguments,
                    "reason": "planned_knowledge_lookup",
                }

    content = await create_text_response(
        model=settings.chat_model,
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

    if not state.review_content:
        return {"action": "generate_stage", "stage": "review", "reason": "rule_fallback_missing_review"}
    if not state.test_suggestion_content:
        return {"action": "generate_stage", "stage": "test_suggestion", "reason": "rule_fallback_missing_test_suggestion"}
    if not state.unit_test_generation_content:
        return {"action": "generate_stage", "stage": "unit_test", "reason": "rule_fallback_missing_unit_test"}
    return {"action": "finish", "reason": "rule_fallback_all_completed"}


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
        output = build_pr_meta_tool_result(repo, pr_data, files)
        sources: list[dict[str, Any]] = []
    elif tool_name == "get_pr_diff":
        output = build_pr_diff_tool_result(state.diff_text)
        sources = []
    elif tool_name == "search_review_knowledge":
        output, sources = await search_review_knowledge(str(arguments.get("query") or ""))
        if sources:
            state.knowledge_sources.extend(sources)
    else:
        output = await list_recent_repo_tasks(db, state.repo_id, current_task_id)
        sources = []

    state.tool_calls.append(AgentToolRecord(name=tool_name, arguments=arguments, output_preview=_truncate(output, 280)))
    state.executed_steps.append(f"tool:{tool_name}")


async def _generate_stage(state: PRReviewAgentState, stage: str) -> None:
    user_prompt = _build_stage_prompt(state)
    content = ""
    if stage == "review":
        content = await _safe_markdown_completion(REVIEW_SYSTEM_PROMPT, user_prompt)
        state.review_content = content
    elif stage == "test_suggestion":
        content = await _safe_markdown_completion(TEST_SYSTEM_PROMPT, user_prompt, TEST_SYSTEM_PROMPT_COMPACT)
        state.test_suggestion_content = content
    elif stage == "unit_test":
        content = await _safe_markdown_completion(
            UNIT_TEST_GENERATION_PROMPT, user_prompt, UNIT_TEST_GENERATION_PROMPT_COMPACT
        )
        state.unit_test_generation_content = content
    if content.startswith("生成失败："):
        state.fallback_events.append(f"stage_failed:{stage}")
    state.executed_steps.append(f"stage:{stage}")


async def _build_execution_summary(state: PRReviewAgentState) -> str:
    tool_names = ", ".join(record.name for record in state.tool_calls) or "无"
    prompt = (
        f"计划：{json.dumps(asdict(state.plan), ensure_ascii=False)}\n"
        f"工具调用：{json.dumps([asdict(item) for item in state.tool_calls], ensure_ascii=False)}\n"
        f"重规划：{json.dumps(state.replans, ensure_ascii=False)}\n"
        f"兜底事件：{json.dumps(state.fallback_events, ensure_ascii=False)}\n"
        f"阶段完成：review={bool(state.review_content)}, test_suggestion={bool(state.test_suggestion_content)}, unit_test={bool(state.unit_test_generation_content)}"
    )
    return await _safe_markdown_completion(PR_REVIEW_AGENT_REPORTER_PROMPT, prompt)


async def run_pr_review_agent(task: AgentTask, repo: GitHubRepository, db: AsyncSession) -> PRReviewAgentState:
    pr_data = await fetch_pull_request(repo, task.pr_number or 0)
    files = await fetch_pull_request_files(repo, task.pr_number or 0)
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
    )
    state.plan = await _plan_agent(repo, pr_data, files, diff_text)
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
                "review": bool(state.review_content),
                "test": bool(state.test_suggestion_content),
                "unit": bool(state.unit_test_generation_content),
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
                await _generate_stage(state, stage)
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
        if not state.review_content:
            await _generate_stage(state, "review")
        elif not state.test_suggestion_content:
            await _generate_stage(state, "test_suggestion")
        elif not state.unit_test_generation_content:
            await _generate_stage(state, "unit_test")
        else:
            break

    if not state.review_content:
        await _replan_agent(state, "review_missing_after_loop")
        await _generate_stage(state, "review")
    if not state.test_suggestion_content:
        await _replan_agent(state, "test_suggestion_missing_after_loop")
        await _generate_stage(state, "test_suggestion")
    if not state.unit_test_generation_content:
        await _replan_agent(state, "unit_test_missing_after_loop")
        await _generate_stage(state, "unit_test")

    state.execution_summary = await _build_execution_summary(state)
    task.title = state.pr_title
    task.commit_sha = pr_data.get("head", {}).get("sha") or task.commit_sha
    task.review_content = state.review_content
    task.test_suggestion_content = state.test_suggestion_content
    task.unit_test_generation_content = state.unit_test_generation_content
    task.source_payload = merge_agent_payload(
        task.source_payload,
        {
            "mode": "pr_review_agent",
            "plan": asdict(state.plan),
            "executed_steps": state.executed_steps,
            "tool_calls": [asdict(item) for item in state.tool_calls],
            "replans": state.replans,
            "fallback_events": state.fallback_events,
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
