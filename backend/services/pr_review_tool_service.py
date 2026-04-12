import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from services.llm_service import get_chat_client, get_embedding_client
from services.rag_service import filter_relevant_chunks, hybrid_retrieve

logger = logging.getLogger(__name__)


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
