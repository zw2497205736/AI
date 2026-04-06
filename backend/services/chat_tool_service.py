import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.agent_task import AgentTask
from models.document import Document
from models.github_repository import GitHubRepository
from prompts.tool import AGENT_FINAL_RESPONSE_PROMPT, AGENT_NEXT_ACTION_PROMPT, TOOL_RESPONSE_PROMPT, TOOL_SELECTION_PROMPT
from services.llm_service import create_text_response
from services.rag_service import filter_relevant_chunks, hybrid_retrieve

logger = logging.getLogger(__name__)

SUPPORTED_TOOLS = {
    "none",
    "list_connected_repositories",
    "list_recent_github_tasks",
    "get_github_task_detail",
    "list_documents",
    "search_knowledge_base",
}


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", "", query).lower()


def _extract_task_id(query: str) -> int | None:
    match = re.search(r"(?:任务|task)\s*#?\s*(\d+)", query, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _select_tool_by_rules(query: str) -> dict[str, Any] | None:
    normalized = _normalize_query(query)
    fallback_task_id = _extract_task_id(query)

    if fallback_task_id is not None and any(keyword in normalized for keyword in ["任务", "task", "结果", "详情", "审查"]):
        return {"tool": "get_github_task_detail", "arguments": {"task_id": fallback_task_id}}

    repository_keywords = ["仓库", "repo", "repository", "github仓", "接入", "连接"]
    count_keywords = ["几个", "多少", "数量", "列表", "哪些", "查看"]
    if any(keyword in normalized for keyword in repository_keywords) and any(keyword in normalized for keyword in count_keywords):
        return {"tool": "list_connected_repositories", "arguments": {}}

    task_keywords = ["任务", "pr", "审查", "review", "检查", "执行记录", "最近"]
    if any(keyword in normalized for keyword in task_keywords) and any(keyword in normalized for keyword in ["最近", "哪些", "列表", "记录", "情况"]):
        return {"tool": "list_recent_github_tasks", "arguments": {}}

    document_keywords = ["文档", "知识库文件", "资料", "文件列表", "上传了什么", "有哪些文件"]
    if any(keyword in normalized for keyword in document_keywords):
        return {"tool": "list_documents", "arguments": {}}

    knowledge_base_keywords = ["知识库", "资料里", "文档里", "检索", "搜索", "查知识库", "查文档"]
    if any(keyword in normalized for keyword in knowledge_base_keywords):
        return {"tool": "search_knowledge_base", "arguments": {"query": query}}

    return None


async def _select_tool(query: str) -> dict[str, Any]:
    fallback_task_id = _extract_task_id(query)
    rule_selected = _select_tool_by_rules(query)
    if rule_selected is not None:
        return rule_selected
    try:
        content = await create_text_response(
            model=settings.chat_model,
            input_messages=[{"role": "user", "content": TOOL_SELECTION_PROMPT.format(query=query)}],
            max_output_tokens=120,
            temperature=0.1,
            text_format={"format": {"type": "json_object"}},
        )
        parsed = json.loads(content or "{}")
        tool_name = str(parsed.get("tool") or "none")
        arguments = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
        if tool_name not in SUPPORTED_TOOLS:
            tool_name = "none"
        if tool_name == "get_github_task_detail" and "task_id" not in arguments and fallback_task_id is not None:
            arguments["task_id"] = fallback_task_id
        if tool_name == "search_knowledge_base" and not arguments.get("query"):
            arguments["query"] = query
        return {"tool": tool_name, "arguments": arguments}
    except Exception:
        if fallback_task_id is not None:
            return {"tool": "get_github_task_detail", "arguments": {"task_id": fallback_task_id}}
        return {"tool": "none", "arguments": {}}


def format_tool_history(tool_history: list[dict[str, Any]]) -> str:
    if not tool_history:
        return "（暂无）"
    lines: list[str] = []
    for index, item in enumerate(tool_history, start=1):
        lines.append(
            f"[{index}] tool={item.get('tool_name')} args={json.dumps(item.get('arguments', {}), ensure_ascii=False)}\n结果：{item.get('tool_result', '')}"
        )
    return "\n\n".join(lines)


async def _list_connected_repositories(user_id: str, db: AsyncSession) -> tuple[str, list[dict], bool]:
    result = await db.execute(
        select(GitHubRepository)
        .where(GitHubRepository.user_id == user_id)
        .order_by(GitHubRepository.created_at.desc(), GitHubRepository.id.desc())
    )
    repos = result.scalars().all()
    if not repos:
        return "当前还没有接入任何 GitHub 仓库。", [], False
    lines = [
        f"{index + 1}. {repo.display_name}（owner={repo.repo_owner}, repo={repo.repo_name}, 状态={'启用' if repo.is_active else '停用'}）"
        for index, repo in enumerate(repos[:10])
    ]
    return "\n".join(lines), [], False


async def _list_recent_github_tasks(user_id: str, db: AsyncSession) -> tuple[str, list[dict], bool]:
    result = await db.execute(
        select(AgentTask).where(AgentTask.user_id == user_id).order_by(AgentTask.created_at.desc(), AgentTask.id.desc()).limit(10)
    )
    tasks = result.scalars().all()
    if not tasks:
        return "当前还没有 GitHub PR 审查任务。", [], False
    repo_ids = {task.repo_id for task in tasks}
    repo_map: dict[int, str] = {}
    if repo_ids:
        repo_result = await db.execute(select(GitHubRepository).where(GitHubRepository.id.in_(repo_ids)))
        repo_map = {repo.id: repo.display_name for repo in repo_result.scalars().all()}
    lines = []
    for task in tasks:
        lines.append(
            f"- task_id={task.id} | 仓库={repo_map.get(task.repo_id, '未知仓库')} | PR=#{task.pr_number or '-'} | 标题={task.title} | 状态={task.status}"
        )
    return "\n".join(lines), [], False


async def _get_github_task_detail(user_id: str, db: AsyncSession, task_id: int | None) -> tuple[str, list[dict], bool]:
    if not task_id:
        return "没有提供有效的任务 ID。", [], False
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return f"没有找到 task_id={task_id} 的任务。", [], False
    repo_name = "未知仓库"
    repo = await db.get(GitHubRepository, task.repo_id)
    if repo is not None:
        repo_name = repo.display_name
    parts = [
        f"任务 ID：{task.id}",
        f"仓库：{repo_name}",
        f"标题：{task.title}",
        f"状态：{task.status}",
        f"事件：{task.event_type}",
        f"PR 编号：{task.pr_number or '-'}",
    ]
    if task.review_content:
        parts.append(f"Code Review：{task.review_content[:1200]}")
    if task.test_suggestion_content:
        parts.append(f"测试建议：{task.test_suggestion_content[:1200]}")
    if task.unit_test_generation_content:
        parts.append(f"单元测试建议：{task.unit_test_generation_content[:1200]}")
    if task.error_message:
        parts.append(f"错误信息：{task.error_message[:500]}")
    return "\n".join(parts), [], False


async def _list_documents(db: AsyncSession) -> tuple[str, list[dict], bool]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc(), Document.id.desc()).limit(10))
    documents = result.scalars().all()
    if not documents:
        return "当前知识库还没有文档。", [], False
    lines = [
        f"- doc_id={doc.id} | 文件={doc.filename} | 状态={doc.status} | 分块数={doc.chunk_count}"
        for doc in documents
    ]
    return "\n".join(lines), [], False


async def _search_knowledge_base(query: str, embedding_client, chat_client) -> tuple[str, list[dict], bool]:
    raw_chunks = await hybrid_retrieve(query, embedding_client)
    chunks = await filter_relevant_chunks(query, raw_chunks, chat_client)
    if not chunks:
        return "知识库中没有检索到与该问题直接相关的内容。", [], False
    lines = []
    for index, item in enumerate(chunks[:5], start=1):
        preview = " ".join(str(item.get("content") or "").split())
        if len(preview) > 200:
            preview = preview[:200].rstrip() + "..."
        lines.append(f"[{index}] 文件：{item.get('filename', '未命名文档')} | 片段：{preview}")
    return "\n".join(lines), chunks, True


async def maybe_run_chat_tool(query: str, user_id: str, db: AsyncSession, embedding_client, chat_client) -> dict[str, Any] | None:
    selection = await _select_tool(query)
    tool_name = selection["tool"]
    arguments = selection["arguments"]
    if tool_name == "none":
        return None

    logger.info("Chat tool selected: user=%s tool=%s arguments=%s", user_id, tool_name, arguments)

    if tool_name == "list_connected_repositories":
        result_text, sources, retrieval_hit = await _list_connected_repositories(user_id, db)
    elif tool_name == "list_recent_github_tasks":
        result_text, sources, retrieval_hit = await _list_recent_github_tasks(user_id, db)
    elif tool_name == "get_github_task_detail":
        result_text, sources, retrieval_hit = await _get_github_task_detail(user_id, db, arguments.get("task_id"))
    elif tool_name == "list_documents":
        result_text, sources, retrieval_hit = await _list_documents(db)
    elif tool_name == "search_knowledge_base":
        result_text, sources, retrieval_hit = await _search_knowledge_base(str(arguments.get("query") or query), embedding_client, chat_client)
    else:
        return None

    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_result": result_text,
        "sources": sources,
        "retrieval_hit": retrieval_hit,
    }


async def select_chat_tool(query: str) -> dict[str, Any]:
    return await _select_tool(query)


async def plan_chat_agent_step(query: str, tool_history: list[dict[str, Any]]) -> dict[str, Any]:
    if not tool_history:
        selection = await _select_tool(query)
        if selection["tool"] != "none":
            return {"action": "tool_call", "tool": selection["tool"], "arguments": selection["arguments"]}
    try:
        content = await create_text_response(
            model=settings.chat_model,
            input_messages=[
                {
                    "role": "user",
                    "content": AGENT_NEXT_ACTION_PROMPT.format(query=query, tool_history=format_tool_history(tool_history)),
                }
            ],
            max_output_tokens=160,
            temperature=0.1,
            text_format={"format": {"type": "json_object"}},
        )
        parsed = json.loads(content or "{}")
        action = str(parsed.get("action") or "direct_answer")
        tool_name = str(parsed.get("tool") or "")
        arguments = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
        if action != "tool_call":
            return {"action": "direct_answer", "tool": "", "arguments": {}}
        if tool_name not in SUPPORTED_TOOLS or tool_name == "none":
            return {"action": "direct_answer", "tool": "", "arguments": {}}
        if tool_name == "search_knowledge_base" and not arguments.get("query"):
            arguments["query"] = query
        return {"action": "tool_call", "tool": tool_name, "arguments": arguments}
    except Exception:
        return {"action": "direct_answer", "tool": "", "arguments": {}}


async def execute_chat_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    query: str,
    user_id: str,
    db: AsyncSession,
    embedding_client,
    chat_client,
) -> dict[str, Any] | None:
    logger.info("Chat tool selected: user=%s tool=%s arguments=%s", user_id, tool_name, arguments)
    if tool_name == "list_connected_repositories":
        result_text, sources, retrieval_hit = await _list_connected_repositories(user_id, db)
    elif tool_name == "list_recent_github_tasks":
        result_text, sources, retrieval_hit = await _list_recent_github_tasks(user_id, db)
    elif tool_name == "get_github_task_detail":
        result_text, sources, retrieval_hit = await _get_github_task_detail(user_id, db, arguments.get("task_id"))
    elif tool_name == "list_documents":
        result_text, sources, retrieval_hit = await _list_documents(db)
    elif tool_name == "search_knowledge_base":
        result_text, sources, retrieval_hit = await _search_knowledge_base(str(arguments.get("query") or query), embedding_client, chat_client)
    else:
        return None
    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_result": result_text,
        "sources": sources,
        "retrieval_hit": retrieval_hit,
    }


async def build_agent_final_answer(query: str, tool_history: list[dict[str, Any]]) -> str:
    try:
        return await create_text_response(
            model=settings.chat_model,
            input_messages=[
                {
                    "role": "user",
                    "content": AGENT_FINAL_RESPONSE_PROMPT.format(query=query, tool_history=format_tool_history(tool_history)),
                }
            ],
            max_output_tokens=1200,
            temperature=0.3,
        )
    except Exception:
        if tool_history:
            return tool_history[-1].get("tool_result", "") or "当前没有查到相关数据。"
        return "当前没有查到相关数据。"


async def build_tool_answer(query: str, tool_name: str, tool_result: str) -> str:
    try:
        return await create_text_response(
            model=settings.chat_model,
            input_messages=[
                {
                    "role": "user",
                    "content": TOOL_RESPONSE_PROMPT.format(query=query, tool_name=tool_name, tool_result=tool_result),
                }
            ],
            max_output_tokens=1200,
            temperature=0.3,
        )
    except Exception:
        return tool_result
