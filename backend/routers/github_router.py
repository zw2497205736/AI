import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from schemas.github import GitHubRepositoryCreatePayload
from services.agent_service import list_user_tasks, process_agent_task
from services.github_service import (
    encrypt_github_token,
    serialize_payload,
    verify_github_signature,
    verify_repository_access,
)


router = APIRouter(prefix="/api/github", tags=["github-agent"])


def _extract_task_signal(task: AgentTask) -> tuple[dict | None, dict | None]:
    if not task.source_payload:
        return None, None
    try:
        payload = json.loads(task.source_payload)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    agent_trace = payload.get("agent_trace") if isinstance(payload.get("agent_trace"), dict) else {}
    manual_handoff = agent_trace.get("manual_handoff") if isinstance(agent_trace.get("manual_handoff"), dict) else None
    alert = agent_trace.get("alert") if isinstance(agent_trace.get("alert"), dict) else None
    return manual_handoff, alert


def _extract_agent_trace(task: AgentTask) -> dict:
    if not task.source_payload:
        return {}
    try:
        payload = json.loads(task.source_payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    agent_trace = payload.get("agent_trace")
    return agent_trace if isinstance(agent_trace, dict) else {}


def _build_webhook_url(request: Request, repo_id: int) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/github/webhook/{repo_id}"


def _task_time(task: AgentTask) -> datetime | None:
    return task.updated_at or task.created_at


def _day_bucket(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


async def _get_owned_repo(repo_id: int, user_id: str, db: AsyncSession) -> GitHubRepository:
    result = await db.execute(select(GitHubRepository).where(GitHubRepository.id == repo_id, GitHubRepository.user_id == user_id))
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.get("/repositories")
async def list_repositories(request: Request, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(GitHubRepository).where(GitHubRepository.user_id == current_user.username).order_by(GitHubRepository.created_at.desc(), GitHubRepository.id.desc())
    )
    repos = result.scalars().all()
    return [
        {
            "id": repo.id,
            "repo_owner": repo.repo_owner,
            "repo_name": repo.repo_name,
            "display_name": repo.display_name,
            "is_active": repo.is_active,
            "webhook_url": _build_webhook_url(request, repo.id),
            "webhook_secret_preview": f"{repo.webhook_secret[:3]}***",
            "token_preview": "已加密保存" if repo.github_token_encrypted else "",
            "created_at": repo.created_at.isoformat() if repo.created_at else "",
        }
        for repo in repos
    ]


@router.post("/repositories")
async def create_repository(
    payload: GitHubRepositoryCreatePayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    repo_info = await verify_repository_access(payload.repo_owner.strip(), payload.repo_name.strip(), payload.github_token.strip())
    existing_result = await db.execute(
        select(GitHubRepository).where(
            GitHubRepository.user_id == current_user.username,
            GitHubRepository.repo_owner == payload.repo_owner.strip(),
            GitHubRepository.repo_name == payload.repo_name.strip(),
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Repository already connected")

    repo = GitHubRepository(
        user_id=current_user.username,
        repo_owner=payload.repo_owner.strip(),
        repo_name=payload.repo_name.strip(),
        display_name=payload.display_name.strip() or repo_info.get("full_name") or f"{payload.repo_owner}/{payload.repo_name}",
        github_token_encrypted=encrypt_github_token(payload.github_token.strip()),
        webhook_secret=payload.webhook_secret.strip(),
        is_active=True,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return {
        "id": repo.id,
        "display_name": repo.display_name,
        "webhook_url": _build_webhook_url(request, repo.id),
    }


@router.delete("/repositories/{repo_id}")
async def delete_repository(repo_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    repo = await _get_owned_repo(repo_id, current_user.username, db)
    await db.delete(repo)
    await db.commit()
    return {"status": "ok"}


@router.get("/tasks")
async def get_tasks(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    tasks = await list_user_tasks(current_user.username, db)
    repo_ids = {task.repo_id for task in tasks}
    repo_map: dict[int, GitHubRepository] = {}
    if repo_ids:
        repo_result = await db.execute(select(GitHubRepository).where(GitHubRepository.id.in_(repo_ids)))
        repo_map = {repo.id: repo for repo in repo_result.scalars().all()}
    return [
        {
            "id": task.id,
            "repo_id": task.repo_id,
            "repo_display_name": repo_map.get(task.repo_id).display_name if repo_map.get(task.repo_id) else "未知仓库",
            "task_type": task.task_type,
            "event_type": task.event_type,
            "pr_number": task.pr_number,
            "commit_sha": task.commit_sha,
            "title": task.title,
            "status": task.status,
            "error_message": task.error_message,
            "manual_handoff": _extract_task_signal(task)[0],
            "alert": _extract_task_signal(task)[1],
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
        }
        for task in tasks
    ]


@router.get("/dashboard")
async def get_dashboard(
    days: int = 7,
    repo_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tasks = await list_user_tasks(current_user.username, db)
    normalized_days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=normalized_days - 1)
    filtered_tasks = []
    for task in tasks:
        if repo_id is not None and task.repo_id != repo_id:
            continue
        task_time = _task_time(task)
        if task_time is None:
            continue
        if task_time.tzinfo is None:
            task_time = task_time.replace(tzinfo=timezone.utc)
        if task_time >= since:
            filtered_tasks.append(task)
    tasks = filtered_tasks
    repo_ids = {task.repo_id for task in tasks}
    repo_map: dict[int, GitHubRepository] = {}
    if repo_ids:
        repo_result = await db.execute(select(GitHubRepository).where(GitHubRepository.id.in_(repo_ids)))
        repo_map = {repo.id: repo for repo in repo_result.scalars().all()}

    status_counts: dict[str, int] = {}
    error_category_counts: dict[str, int] = {}
    recovery_counts: dict[str, int] = {}
    repo_counts: dict[str, int] = {}
    total_duration_ms = 0
    duration_samples = 0
    manual_handoff_count = 0
    alert_count = 0
    checkpoint_hit_count = 0
    trend_map: dict[str, dict[str, int]] = {}

    for task in tasks:
        status_counts[task.status] = status_counts.get(task.status, 0) + 1
        repo_name = repo_map.get(task.repo_id).display_name if repo_map.get(task.repo_id) else f"repo:{task.repo_id}"
        repo_counts[repo_name] = repo_counts.get(repo_name, 0) + 1
        task_time = _task_time(task)
        if task_time is not None:
            if task_time.tzinfo is None:
                task_time = task_time.replace(tzinfo=timezone.utc)
            bucket = _day_bucket(task_time)
            trend = trend_map.setdefault(
                bucket,
                {"task_count": 0, "manual_handoff_count": 0, "alert_count": 0, "failed_count": 0},
            )
            trend["task_count"] += 1
            if task.status in {"failed", "partial_completed"}:
                trend["failed_count"] += 1

        manual_handoff, alert = _extract_task_signal(task)
        if manual_handoff:
            manual_handoff_count += 1
            if task_time is not None:
                trend_map[_day_bucket(task_time)]["manual_handoff_count"] += 1
        if alert and alert.get("required"):
            alert_count += 1
            if task_time is not None:
                trend_map[_day_bucket(task_time)]["alert_count"] += 1

        agent_trace = _extract_agent_trace(task)
        observability = agent_trace.get("observability") if isinstance(agent_trace.get("observability"), dict) else {}
        if isinstance(observability.get("total_duration_ms"), int):
            total_duration_ms += int(observability["total_duration_ms"])
            duration_samples += 1
        checkpoint_hits = observability.get("checkpoint_hits")
        if isinstance(checkpoint_hits, list):
            checkpoint_hit_count += len(checkpoint_hits)

        error_events = agent_trace.get("error_events")
        if isinstance(error_events, list):
            for item in error_events:
                if not isinstance(item, dict):
                    continue
                category = str(item.get("category") or "unknown_error")
                recovery = str(item.get("recovery") or "unknown")
                error_category_counts[category] = error_category_counts.get(category, 0) + 1
                recovery_counts[recovery] = recovery_counts.get(recovery, 0) + 1

    top_repositories = sorted(repo_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    recent_tasks = tasks[:8]
    ordered_days = [
        _day_bucket((since + timedelta(days=offset)))
        for offset in range(normalized_days)
    ]
    return {
        "summary": {
            "task_count": len(tasks),
            "manual_handoff_count": manual_handoff_count,
            "alert_count": alert_count,
            "checkpoint_hit_count": checkpoint_hit_count,
            "avg_duration_ms": int(total_duration_ms / duration_samples) if duration_samples else 0,
            "days": normalized_days,
            "repo_id": repo_id,
        },
        "status_counts": status_counts,
        "error_category_counts": error_category_counts,
        "recovery_counts": recovery_counts,
        "daily_trends": [
            {
                "day": day,
                **trend_map.get(day, {"task_count": 0, "manual_handoff_count": 0, "alert_count": 0, "failed_count": 0}),
            }
            for day in ordered_days
        ],
        "top_repositories": [
            {"repo_display_name": repo_name, "task_count": task_count}
            for repo_name, task_count in top_repositories
        ],
        "recent_tasks": [
            {
                "id": task.id,
                "repo_display_name": repo_map.get(task.repo_id).display_name if repo_map.get(task.repo_id) else "未知仓库",
                "pr_number": task.pr_number,
                "title": task.title,
                "status": task.status,
                "manual_handoff": _extract_task_signal(task)[0],
                "alert": _extract_task_signal(task)[1],
                "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            }
            for task in recent_tasks
        ],
    }


@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == current_user.username))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "repo_id": task.repo_id,
        "task_type": task.task_type,
        "event_type": task.event_type,
        "pr_number": task.pr_number,
        "commit_sha": task.commit_sha,
        "title": task.title,
        "status": task.status,
        "review_content": task.review_content or "",
        "test_suggestion_content": task.test_suggestion_content or "",
        "unit_test_generation_content": task.unit_test_generation_content or "",
        "error_message": task.error_message,
        "source_payload": json.loads(task.source_payload) if task.source_payload else None,
        "manual_handoff": _extract_task_signal(task)[0],
        "alert": _extract_task_signal(task)[1],
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
    }


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == current_user.username))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    rerun = AgentTask(
        repo_id=task.repo_id,
        user_id=task.user_id,
        task_type=task.task_type,
        event_type=task.event_type,
        pr_number=task.pr_number,
        commit_sha=task.commit_sha,
        title=task.title,
        status="queued",
        source_payload=task.source_payload,
    )
    db.add(rerun)
    await db.commit()
    await db.refresh(rerun)
    asyncio.create_task(process_agent_task(rerun.id))
    return {"id": rerun.id, "status": "queued"}


@router.post("/webhook/{repo_id}")
async def github_webhook(repo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    repo = await db.get(GitHubRepository, repo_id)
    if repo is None or not repo.is_active:
        raise HTTPException(status_code=404, detail="Repository not found")

    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(raw_body, repo.webhook_secret, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"Unsupported event: {event_type}"}

    action = payload.get("action", "")
    if action not in {"opened", "reopened", "synchronize"}:
        return {"status": "ignored", "reason": f"Unsupported action: {action}"}

    pull_request = payload.get("pull_request") or {}
    pr_number = pull_request.get("number") or payload.get("number")
    commit_sha = (pull_request.get("head") or {}).get("sha")
    existing_result = await db.execute(
        select(AgentTask)
        .where(
            AgentTask.repo_id == repo.id,
            AgentTask.task_type == "pr_review",
            AgentTask.pr_number == pr_number,
            AgentTask.commit_sha == commit_sha,
        )
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
    )
    existing_task = existing_result.scalar_one_or_none()
    if existing_task is not None:
        return {
            "status": "duplicate",
            "task_id": existing_task.id,
            "task_status": existing_task.status,
            "reason": "Task already exists for this PR head commit",
        }

    task = AgentTask(
        repo_id=repo.id,
        user_id=repo.user_id,
        task_type="pr_review",
        event_type=action,
        pr_number=pr_number,
        commit_sha=commit_sha,
        title=pull_request.get("title") or f"PR #{payload.get('number')}",
        status="queued",
        source_payload=serialize_payload(
            {
                "action": action,
                "number": payload.get("number"),
                "repository": (payload.get("repository") or {}).get("full_name"),
                "pull_request": {
                    "title": pull_request.get("title"),
                    "html_url": pull_request.get("html_url"),
                    "base_ref": (pull_request.get("base") or {}).get("ref"),
                    "head_ref": (pull_request.get("head") or {}).get("ref"),
                },
            }
        ),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    asyncio.create_task(process_agent_task(task.id))
    return {"status": "accepted", "task_id": task.id}
