import json
import logging
from typing import Any

import httpx

from config import settings
from models.github_repository import GitHubRepository
from services.github_service import decrypt_github_token, fetch_pull_request, fetch_pull_request_files, fetch_pull_requests

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-03-26"


class GitHubMCPError(RuntimeError):
    pass


async def _post_mcp_message(token: str, payload: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    async with httpx.AsyncClient(timeout=settings.github_mcp_timeout) as client:
        response = await client.post(settings.github_mcp_url, headers=headers, json=payload)
    response.raise_for_status()
    next_session_id = response.headers.get("Mcp-Session-Id") or session_id
    text = response.text.strip()
    if not text:
        return {}, next_session_id
    if text.startswith("data: "):
        lines = [line[6:] for line in text.splitlines() if line.startswith("data: ")]
        for line in reversed(lines):
            if not line.strip() or line.strip() == "[DONE]":
                continue
            return json.loads(line), next_session_id
        return {}, next_session_id
    return response.json(), next_session_id


async def _initialize_mcp_session(token: str) -> str | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "ai-rd-collab-platform", "version": "0.1.0"},
        },
    }
    _, session_id = await _post_mcp_message(token, payload)
    if session_id:
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        await _post_mcp_message(token, notification, session_id=session_id)
    return session_id


async def _list_tools(token: str, session_id: str) -> list[dict[str, Any]]:
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    data, _ = await _post_mcp_message(token, payload, session_id=session_id)
    tools = (((data.get("result") or {}).get("tools")) if isinstance(data, dict) else None) or []
    return tools if isinstance(tools, list) else []


def _find_tool_name(tools: list[dict[str, Any]], *keywords: str) -> str | None:
    lowered = [keyword.lower() for keyword in keywords]
    for tool in tools:
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        haystack = f"{name} {description}".lower()
        if all(keyword in haystack for keyword in lowered):
            return name
    for tool in tools:
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        haystack = f"{name} {description}".lower()
        if any(keyword in haystack for keyword in lowered):
            return name
    return None


async def _call_tool(token: str, session_id: str, tool_name: str, arguments: dict[str, Any]) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    data, _ = await _post_mcp_message(token, payload, session_id=session_id)
    if not isinstance(data, dict):
        raise GitHubMCPError("Invalid MCP response")
    if data.get("error"):
        raise GitHubMCPError(str(data["error"]))
    return (data.get("result") or {}).get("content") or (data.get("result") or {})


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)


async def _run_github_mcp_tool(repo: GitHubRepository, tool_type: str, arguments: dict[str, Any]) -> str:
    token = decrypt_github_token(repo.github_token_encrypted)
    session_id = await _initialize_mcp_session(token)
    if not session_id:
        raise GitHubMCPError("MCP session initialization failed")
    tools = await _list_tools(token, session_id)
    if not tools:
        raise GitHubMCPError("No tools discovered from GitHub MCP")
    if tool_type == "list_pull_requests":
        tool_name = _find_tool_name(tools, "pull", "list") or _find_tool_name(tools, "pull", "request")
    elif tool_type == "get_pull_request":
        tool_name = _find_tool_name(tools, "pull", "request", "get") or _find_tool_name(tools, "pull", "request")
    elif tool_type == "get_pull_request_files":
        tool_name = _find_tool_name(tools, "pull", "file") or _find_tool_name(tools, "pull", "diff")
    else:
        tool_name = None
    if not tool_name:
        raise GitHubMCPError(f"No matching GitHub MCP tool found for {tool_type}")
    logger.info("Using GitHub MCP tool: repo=%s/%s tool_type=%s tool_name=%s", repo.repo_owner, repo.repo_name, tool_type, tool_name)
    content = await _call_tool(token, session_id, tool_name, arguments)
    return _content_to_text(content)


async def github_mcp_list_pull_requests(repo: GitHubRepository, *, state: str = "open", per_page: int = 10) -> str:
    if settings.github_mcp_enabled:
        try:
            return await _run_github_mcp_tool(
                repo,
                "list_pull_requests",
                {"owner": repo.repo_owner, "repo": repo.repo_name, "state": state, "per_page": per_page},
            )
        except Exception as exc:
            logger.warning("GitHub MCP list_pull_requests failed, falling back to REST: %s", exc)
    pulls = await fetch_pull_requests(repo, state=state, per_page=per_page)
    if not pulls:
        return f"{repo.display_name} 当前没有 {state} 状态的 PR。"
    lines = [
        f"- PR #{item.get('number')} | 标题={item.get('title')} | 状态={item.get('state')} | 作者={(item.get('user') or {}).get('login', '-')}"
        for item in pulls
    ]
    return "\n".join(lines)


async def github_mcp_get_pull_request(repo: GitHubRepository, pr_number: int) -> str:
    if settings.github_mcp_enabled:
        try:
            return await _run_github_mcp_tool(
                repo,
                "get_pull_request",
                {"owner": repo.repo_owner, "repo": repo.repo_name, "pullNumber": pr_number},
            )
        except Exception as exc:
            logger.warning("GitHub MCP get_pull_request failed, falling back to REST: %s", exc)
    pr = await fetch_pull_request(repo, pr_number)
    return "\n".join(
        [
            f"PR #{pr.get('number')}",
            f"标题：{pr.get('title')}",
            f"状态：{pr.get('state')}",
            f"作者：{(pr.get('user') or {}).get('login', '-')}",
            f"目标分支：{((pr.get('base') or {}).get('ref')) or '-'}",
            f"来源分支：{((pr.get('head') or {}).get('ref')) or '-'}",
            f"链接：{pr.get('html_url')}",
        ]
    )


async def github_mcp_get_pull_request_files(repo: GitHubRepository, pr_number: int) -> str:
    if settings.github_mcp_enabled:
        try:
            return await _run_github_mcp_tool(
                repo,
                "get_pull_request_files",
                {"owner": repo.repo_owner, "repo": repo.repo_name, "pullNumber": pr_number},
            )
        except Exception as exc:
            logger.warning("GitHub MCP get_pull_request_files failed, falling back to REST: %s", exc)
    files = await fetch_pull_request_files(repo, pr_number)
    if not files:
        return f"PR #{pr_number} 没有查到文件变更。"
    lines = [
        f"- {item.get('filename')} | status={item.get('status')} | +{item.get('additions', 0)} / -{item.get('deletions', 0)}"
        for item in files
    ]
    return "\n".join(lines)
