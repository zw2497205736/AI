import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from models.repo_review_memory import RepoReviewMemory
from services.github_service import fetch_commit_check_runs, fetch_issue, fetch_pull_request_commits, search_repository_code
from services.llm_service import get_chat_client, get_embedding_client
from services.rag_service import filter_relevant_chunks, hybrid_retrieve

logger = logging.getLogger(__name__)


def _parse_agent_trace_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    agent_trace = parsed.get("agent_trace")
    return agent_trace if isinstance(agent_trace, dict) else {}


def _extract_changed_files_from_tool_calls(tool_calls: list[dict[str, Any]]) -> set[str]:
    files: set[str] = set()
    for item in tool_calls:
        if not isinstance(item, dict):
            continue
        preview = str(item.get("output_preview") or "")
        for match in re.findall(r"- ([^:\n]+)", preview):
            normalized = match.strip()
            if "/" in normalized or "." in normalized:
                files.add(normalized)
    return files


def build_pr_meta_tool_result(repo: GitHubRepository, pr_data: dict[str, Any], files: list[dict[str, Any]]) -> str:
    filenames = [str(item.get("filename") or "") for item in files if item.get("filename")]
    top_files = "\n".join(f"- {name}" for name in filenames[:10]) or "- 无"
    return (
        f"仓库：{repo.repo_owner}/{repo.repo_name}\n"
        f"PR 标题：{pr_data.get('title', '')}\n"
        f"PR 描述：{pr_data.get('body') or '无'}\n"
        f"目标分支：{pr_data.get('base', {}).get('ref', '')}\n"
        f"来源分支：{pr_data.get('head', {}).get('ref', '')}\n"
        f"变更文件数：{len(files)}\n"
        f"主要变更文件：\n{top_files}"
    )


def build_pr_diff_tool_result(diff_text: str) -> str:
    return diff_text.strip() or "无可用 diff"


async def build_pr_commits_tool_result(repo: GitHubRepository, pr_number: int, limit: int = 8) -> str:
    commits = await fetch_pull_request_commits(repo, pr_number, per_page=limit)
    if not commits:
        return "未获取到 PR commits。"
    lines = []
    for item in commits[:limit]:
        commit = item.get("commit") or {}
        message = str(commit.get("message") or "").splitlines()[0][:120]
        author = (commit.get("author") or {}).get("name") or (item.get("author") or {}).get("login") or "unknown"
        sha = str(item.get("sha") or "")[:8]
        lines.append(f"- {sha} by {author}: {message or '无提交说明'}")
    return "最近 PR commits：\n" + "\n".join(lines)


async def build_pr_checks_tool_result(repo: GitHubRepository, head_sha: str, limit: int = 10) -> str:
    if not head_sha.strip():
        return "缺少 PR head sha，无法查询 checks。"
    check_runs = await fetch_commit_check_runs(repo, head_sha)
    if not check_runs:
        return "未获取到 PR checks，可能仓库未配置 checks。"
    lines = []
    for item in check_runs[:limit]:
        name = str(item.get("name") or "unknown")
        status = str(item.get("status") or "unknown")
        conclusion = str(item.get("conclusion") or "pending")
        app_name = ((item.get("app") or {}).get("name")) or "unknown"
        lines.append(f"- {name}: status={status}, conclusion={conclusion}, app={app_name}")
    return "PR checks：\n" + "\n".join(lines)


def extract_issue_numbers_from_text(*texts: str) -> list[int]:
    matches: list[int] = []
    for text in texts:
        for match in re.findall(r"#(\d+)", text or ""):
            value = int(match)
            if value not in matches:
                matches.append(value)
    return matches[:3]


async def build_issue_context_tool_result(repo: GitHubRepository, issue_numbers: list[int], limit: int = 2) -> str:
    if not issue_numbers:
        return "未识别到关联 issue。"
    blocks: list[str] = []
    for issue_number in issue_numbers[:limit]:
        try:
            issue = await fetch_issue(repo, issue_number)
        except Exception as exc:
            blocks.append(f"- Issue#{issue_number}: 获取失败 {exc}")
            continue
        title = str(issue.get("title") or "无标题")
        state = str(issue.get("state") or "unknown")
        body = str(issue.get("body") or "").strip().replace("\r", "\n")
        blocks.append(
            f"[Issue#{issue_number}] {title}\n"
            f"state={state}\n"
            f"{body[:400] or '无 issue 描述'}"
        )
    return "\n\n".join(blocks) if blocks else "未获取到 issue 背景。"


async def build_code_search_tool_result(repo: GitHubRepository, query: str, limit: int = 5) -> str:
    if not query.strip():
        return "未提供 code search query。"
    items = await search_repository_code(repo, query, per_page=limit)
    if not items:
        return f"未搜索到与 `{query}` 相关的仓库代码。"
    lines = []
    for item in items[:limit]:
        path = str(item.get("path") or "unknown")
        sha = str(item.get("sha") or "")[:8]
        score = item.get("score")
        lines.append(f"- {path} sha={sha} score={score}")
    return f"Code search: {query}\n" + "\n".join(lines)


def infer_dependency_queries_from_diff(diff_text: str, changed_files: list[str], limit: int = 3) -> list[str]:
    candidates: list[str] = []
    for match in re.findall(r"^\+\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", diff_text, re.MULTILINE):
        if match not in candidates:
            candidates.append(match)
    for match in re.findall(r"^\+\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:(]", diff_text, re.MULTILINE):
        if match not in candidates:
            candidates.append(match)
    for filename in changed_files[:3]:
        leaf = filename.rsplit("/", 1)[-1]
        stem = leaf.rsplit(".", 1)[0]
        if len(stem) >= 4 and stem not in candidates:
            candidates.append(stem)
    return candidates[:limit]


async def build_dependency_context_tool_result(
    repo: GitHubRepository,
    diff_text: str,
    changed_files: list[str],
    limit_queries: int = 3,
    limit_hits: int = 3,
) -> str:
    queries = infer_dependency_queries_from_diff(diff_text, changed_files, limit=limit_queries)
    if not queries:
        return "未识别到可用于依赖/调用链搜索的符号。"
    blocks: list[str] = []
    for query in queries:
        items = await search_repository_code(repo, query, per_page=limit_hits)
        if not items:
            blocks.append(f"[{query}] 未搜索到相关实现")
            continue
        lines = []
        for item in items[:limit_hits]:
            path = str(item.get("path") or "unknown")
            sha = str(item.get("sha") or "")[:8]
            lines.append(f"- {path} sha={sha}")
        blocks.append(f"[{query}]\n" + "\n".join(lines))
    return "依赖/调用链相关实现：\n" + "\n\n".join(blocks)


async def search_review_knowledge(query: str) -> tuple[str, list[dict[str, Any]]]:
    if not query.strip():
        return "未提供知识检索 query", []
    embedding_client = get_embedding_client()
    chat_client = get_chat_client()
    try:
        logger.warning("PR review knowledge search started: query=%s", query)
        raw_chunks = await hybrid_retrieve(query, embedding_client)
        logger.warning("PR review knowledge raw hit count: query=%s raw_chunks=%s", query, len(raw_chunks))
        relevant_chunks = await filter_relevant_chunks(query, raw_chunks, chat_client)
        logger.warning("PR review knowledge filtered hit count: query=%s relevant_chunks=%s", query, len(relevant_chunks))
    except Exception as exc:
        logger.exception("PR review knowledge search failed: query=%s", query)
        return f"知识库检索失败，已跳过该步骤：{exc}", []
    if not relevant_chunks:
        return "未命中团队知识库规范。", []
    snippets = []
    for index, item in enumerate(relevant_chunks[: settings.final_top_k], start=1):
        snippets.append(
            f"[{index}] 来源：{item.get('filename', '未命名文档')}\n"
            f"{str(item.get('content') or '')[:500]}"
        )
    return "\n\n".join(snippets), relevant_chunks


async def list_recent_repo_tasks(db: AsyncSession, repo_id: int, current_task_id: int, limit: int = 5) -> str:
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.repo_id == repo_id, AgentTask.id != current_task_id)
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
        .limit(limit)
    )
    tasks = result.scalars().all()
    if not tasks:
        return "该仓库暂无历史审查任务。"
    lines = []
    for task in tasks:
        lines.append(
            f"- Task#{task.id} PR#{task.pr_number or '-'} 状态={task.status} 标题={task.title}"
        )
    return "\n".join(lines)


def _normalize_title_tokens(title: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", (title or "").lower())
        if len(token) >= 4
    }


async def build_related_prs_tool_result(
    db: AsyncSession,
    repo_id: int,
    current_task_id: int,
    pr_title: str,
    changed_files: list[str],
    limit: int = 5,
) -> str:
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.repo_id == repo_id, AgentTask.id != current_task_id, AgentTask.pr_number.is_not(None))
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
        .limit(20)
    )
    tasks = result.scalars().all()
    if not tasks:
        return "仓库中暂无可关联的历史 PR 任务。"

    current_title_tokens = _normalize_title_tokens(pr_title)
    current_files = set(changed_files)
    scored: list[tuple[int, AgentTask, int, int]] = []
    for task in tasks:
        score = 0
        title_overlap = len(current_title_tokens & _normalize_title_tokens(task.title or ""))
        if title_overlap:
            score += title_overlap * 2
        payload = _parse_agent_trace_payload(task.source_payload)
        tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
        historical_files = _extract_changed_files_from_tool_calls(tool_calls)
        file_overlap = len(current_files & historical_files)
        if file_overlap:
            score += file_overlap * 3
        if score > 0:
            scored.append((score, task, title_overlap, file_overlap))

    if not scored:
        return "未找到明显相关的历史 PR。"

    scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    lines = []
    for score, task, title_overlap, file_overlap in scored[:limit]:
        lines.append(
            f"- Task#{task.id} PR#{task.pr_number}: {task.title} "
            f"(score={score}, title_overlap={title_overlap}, file_overlap={file_overlap}, status={task.status})"
        )
    return "相关历史 PR：\n" + "\n".join(lines)


async def build_repo_review_memory(db: AsyncSession, repo_id: int, current_task_id: int, limit: int = 8) -> str:
    persisted_result = await db.execute(select(RepoReviewMemory).where(RepoReviewMemory.repo_id == repo_id))
    persisted_memory = persisted_result.scalar_one_or_none()
    if persisted_memory and persisted_memory.memory_text.strip():
        return persisted_memory.memory_text
    return await build_repo_review_memory_from_tasks(db, repo_id, current_task_id, limit)


async def build_repo_review_memory_from_tasks(db: AsyncSession, repo_id: int, current_task_id: int, limit: int = 8) -> str:
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.repo_id == repo_id, AgentTask.id != current_task_id)
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
        .limit(limit)
    )
    tasks = result.scalars().all()
    completed_tasks = [
        task
        for task in tasks
        if task.review_content or task.test_suggestion_content or task.unit_test_generation_content
    ]
    if not completed_tasks:
        return "暂无可复用的仓库历史审查经验。"

    risk_counter = _count_keywords(
        " ".join(task.review_content or "" for task in completed_tasks),
        {
            "权限/安全": ["权限", "鉴权", "安全", "token", "admin", "越权"],
            "边界条件": ["边界", "空值", "空列表", "非法", "异常输入"],
            "状态一致性": ["状态", "一致性", "回滚", "幂等", "重复", "竞态"],
            "事务/数据": ["事务", "保存", "数据库", "数据", "repository", "save"],
            "兼容性": ["兼容", "调用方", "返回值", "接口"],
        },
    )
    test_counter = _count_keywords(
        " ".join((task.test_suggestion_content or "") + "\n" + (task.unit_test_generation_content or "") for task in completed_tasks),
        {
            "主路径": ["主路径", "正常路径", "成功场景"],
            "边界测试": ["边界", "空值", "空列表", "非法输入"],
            "异常路径": ["异常", "失败", "错误", "抛错"],
            "回归测试": ["回归", "重复", "幂等", "状态切换"],
            "Mock 依赖": ["mock", "模拟", "依赖", "patch"],
        },
    )
    recent_lines = [
        f"- Task#{task.id} PR#{task.pr_number or '-'}：{task.title}（{task.status}）"
        for task in completed_tasks[:3]
    ]
    risk_text = _format_counter(risk_counter) or "暂无明显高频风险模式"
    test_text = _format_counter(test_counter) or "暂无明显高频测试偏好"
    return (
        "仓库历史审查经验：\n"
        f"最近任务：\n{chr(10).join(recent_lines)}\n"
        f"高频风险模式：{risk_text}\n"
        f"高频测试关注：{test_text}\n"
        "使用方式：仅作为审查倾向参考，不要在当前 diff 无证据时强行套用历史问题。"
    )


async def refresh_repo_review_memory(db: AsyncSession, repo_id: int, current_task_id: int, limit: int = 12) -> str:
    memory_text = await build_repo_review_memory_from_tasks(db, repo_id, current_task_id=0, limit=limit)
    task_ids = await _recent_memory_source_task_ids(db, repo_id, current_task_id=0, limit=limit)
    risk_patterns = _extract_line_value(memory_text, "高频风险模式：")
    test_preferences = _extract_line_value(memory_text, "高频测试关注：")

    result = await db.execute(select(RepoReviewMemory).where(RepoReviewMemory.repo_id == repo_id))
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(
            RepoReviewMemory(
                repo_id=repo_id,
                memory_text=memory_text,
                risk_patterns=risk_patterns,
                test_preferences=test_preferences,
                source_task_ids=json.dumps(task_ids, ensure_ascii=False),
            )
        )
    else:
        existing.memory_text = memory_text
        existing.risk_patterns = risk_patterns
        existing.test_preferences = test_preferences
        existing.source_task_ids = json.dumps(task_ids, ensure_ascii=False)
    return memory_text


async def _recent_memory_source_task_ids(db: AsyncSession, repo_id: int, current_task_id: int, limit: int = 12) -> list[int]:
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.repo_id == repo_id, AgentTask.id != current_task_id)
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
        .limit(limit)
    )
    return [task.id for task in result.scalars().all() if task.review_content or task.test_suggestion_content or task.unit_test_generation_content]


def _extract_line_value(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _count_keywords(text: str, keyword_groups: dict[str, list[str]]) -> dict[str, int]:
    normalized = text.lower()
    counter: dict[str, int] = {}
    for label, keywords in keyword_groups.items():
        count = 0
        for keyword in keywords:
            count += len(re.findall(re.escape(keyword.lower()), normalized))
        if count:
            counter[label] = count
    return counter


def _format_counter(counter: dict[str, int], limit: int = 4) -> str:
    items = sorted(counter.items(), key=lambda item: item[1], reverse=True)[:limit]
    return "、".join(f"{label}({count})" for label, count in items)


def merge_agent_payload(existing_payload: str | None, agent_trace: dict[str, Any]) -> str:
    base: dict[str, Any] = {}
    if existing_payload:
        try:
            parsed = json.loads(existing_payload)
            if isinstance(parsed, dict):
                base = parsed
        except json.JSONDecodeError:
            base = {"raw_payload": existing_payload}
    base["agent_trace"] = agent_trace
    return json.dumps(base, ensure_ascii=False)
