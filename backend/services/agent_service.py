import logging
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database import SessionLocal
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from services.alert_service import send_pr_alert
from services.pr_review_agent_service import classify_pr_agent_error, recovery_strategy_for, run_pr_review_agent
from services.pr_review_tool_service import merge_agent_payload

logger = logging.getLogger(__name__)


async def _commit_stage(db, task: AgentTask, *, status: str, error_message: str | None = None):
    task.status = status
    task.error_message = error_message
    await db.commit()


def _is_generation_failed(content: str | None) -> bool:
    return bool(content and content.startswith("生成失败："))


def _is_generation_completed(content: str | None) -> bool:
    return bool(content and content.strip() and not _is_generation_failed(content))


def _build_error_message(category: str, message: str) -> str:
    return f"[{category}] {message}"


def _parse_payload(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_manual_handoff(*, reason: str, severity: str, recommended_actions: list[str], category: str | None = None) -> dict:
    return {
        "required": True,
        "reason": reason,
        "severity": severity,
        "category": category or "",
        "recommended_actions": recommended_actions,
    }


def _failure_manual_handoff(error_category: str, error_message: str) -> dict | None:
    lowered = error_message.lower()
    if error_category == "github_api_error":
        return _build_manual_handoff(
            reason="GitHub 上下文获取失败，系统无法基于完整 PR 信息继续可靠审查。",
            severity="high",
            category=error_category,
            recommended_actions=["检查 GitHub token 权限", "确认仓库 / PR 仍可访问", "修复后重新触发 rerun"],
        )
    if error_category == "empty_diff_error":
        return _build_manual_handoff(
            reason="当前 PR 未获取到可审查 diff，自动审查缺少依据。",
            severity="medium",
            category=error_category,
            recommended_actions=["确认 PR 是否只包含二进制或已被 squash", "检查 GitHub files API 返回", "必要时人工 review"],
        )
    if error_category == "unknown_error" or "403" in lowered or "401" in lowered:
        return _build_manual_handoff(
            reason="任务发生未知或权限相关错误，建议人工确认后再继续自动审查。",
            severity="high",
            category=error_category,
            recommended_actions=["检查日志与 source_payload", "确认仓库权限和外部依赖可用性", "问题修复后 rerun"],
        )
    return None


def _post_run_manual_handoff(task: AgentTask, state) -> dict | None:
    failed_categories = sorted({item.get("category", "unknown_error") for item in state.error_events})
    if "github_api_error" in failed_categories or "empty_diff_error" in failed_categories:
        return _build_manual_handoff(
            reason="本次任务存在关键上下文类失败，自动恢复后仍未完全闭环。",
            severity="high",
            category=",".join(failed_categories),
            recommended_actions=["优先查看 task detail 中的 error_events", "确认 GitHub 上下文是否完整", "必要时人工补充 review 结论"],
        )
    if task.status == "partial_completed":
        return _build_manual_handoff(
            reason="部分阶段生成失败，结果可参考但不应直接视为完整审查。",
            severity="medium",
            category=",".join(failed_categories),
            recommended_actions=["优先人工补看失败阶段", "必要时点击 rerun", "对高风险文件做人工复核"],
        )
    if len(state.fallback_events) >= 4 or len(state.replans) >= 2:
        return _build_manual_handoff(
            reason="本次任务发生多次 fallback / replan，虽然已完成，但建议人工抽查高风险结论。",
            severity="low",
            category="",
            recommended_actions=["抽查 review 结论中的高风险项", "必要时对关键文件做人工复核"],
        )
    return None


def _build_alert_payload(*, task: AgentTask, repo: GitHubRepository, alert: dict, manual_handoff: dict | None = None) -> dict:
    return {
        "type": "pr_agent_alert",
        "task_id": task.id,
        "repo_id": task.repo_id,
        "repo": f"{repo.repo_owner}/{repo.repo_name}",
        "pr_number": task.pr_number,
        "status": task.status,
        "title": task.title,
        "error_message": task.error_message,
        "alert": alert,
        "manual_handoff": manual_handoff,
    }


def _alert_signature(task: AgentTask, alert: dict, manual_handoff: dict | None = None) -> str:
    reason = ""
    if manual_handoff:
        reason = str(manual_handoff.get("reason") or "")
    if not reason:
        reason = str(alert.get("summary") or "")
    return f"{task.repo_id}:{task.pr_number or 0}:{task.status}:{reason.strip()[:160]}"


def _extract_agent_trace(payload: str | None) -> dict:
    parsed = _parse_payload(payload)
    agent_trace = parsed.get("agent_trace")
    return agent_trace if isinstance(agent_trace, dict) else {}


async def _should_dedupe_alert(db, task: AgentTask, alert: dict, manual_handoff: dict | None) -> bool:
    window_minutes = max(1, settings.pr_alert_dedupe_window_minutes)
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    signature = _alert_signature(task, alert, manual_handoff)
    result = await db.execute(
        select(AgentTask)
        .where(
            AgentTask.repo_id == task.repo_id,
            AgentTask.pr_number == task.pr_number,
            AgentTask.id != task.id,
            AgentTask.updated_at >= since,
        )
        .order_by(AgentTask.updated_at.desc(), AgentTask.id.desc())
        .limit(10)
    )
    for item in result.scalars().all():
        agent_trace = _extract_agent_trace(item.source_payload)
        delivery = agent_trace.get("alert_delivery") if isinstance(agent_trace.get("alert_delivery"), dict) else {}
        previous_signature = str(delivery.get("signature") or "")
        previous_delivered = bool(delivery.get("delivered"))
        if previous_signature == signature and previous_delivered:
            return True
    return False


def _clear_failed_generation_placeholders(task: AgentTask) -> None:
    if _is_generation_failed(task.review_content):
        task.review_content = ""
    if _is_generation_failed(task.test_suggestion_content):
        task.test_suggestion_content = ""
    if _is_generation_failed(task.unit_test_generation_content):
        task.unit_test_generation_content = ""


def _initial_running_status(task: AgentTask) -> str:
    if not _is_generation_completed(task.review_content):
        return "running_review"
    if not _is_generation_completed(task.test_suggestion_content):
        return "running_test_suggestion"
    if not _is_generation_completed(task.unit_test_generation_content):
        return "running_unit_test_generation"
    return "running_unit_test_generation"


async def process_agent_task(task_id: int):
    async with SessionLocal() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return
        repo = await db.get(GitHubRepository, task.repo_id)
        if repo is None:
            task.status = "failed"
            task.error_message = "Repository config not found"
            await db.commit()
            return

        task.status = "running"
        task.error_message = None
        await db.commit()
        logger.info("Agent task started: task_id=%s repo_id=%s pr_number=%s", task.id, task.repo_id, task.pr_number)

        try:
            _clear_failed_generation_placeholders(task)
            await _commit_stage(db, task, status=_initial_running_status(task))

            state = await run_pr_review_agent(task, repo, db)
            if _is_generation_completed(task.review_content):
                await _commit_stage(db, task, status="running_test_suggestion")
            if _is_generation_completed(task.test_suggestion_content):
                await _commit_stage(db, task, status="running_unit_test_generation")

            failed_count = sum(
                [
                    _is_generation_failed(task.review_content),
                    _is_generation_failed(task.test_suggestion_content),
                    _is_generation_failed(task.unit_test_generation_content),
                ]
            )
            final_status = "partial_completed" if failed_count else "completed"
            final_error = None
            if failed_count:
                failed_categories = sorted({item.get("category", "unknown_error") for item in state.error_events})
                final_error = _build_error_message(
                    ",".join(failed_categories) or "llm_generation_error",
                    f"{failed_count} 个阶段生成失败",
                )
            await _commit_stage(db, task, status=final_status, error_message=final_error)
            manual_handoff = _post_run_manual_handoff(task, state)
            if manual_handoff:
                alert_payload = {
                    "required": True,
                    "channel": "task_detail",
                    "summary": manual_handoff["reason"],
                }
                dedupe_signature = _alert_signature(task, alert_payload, manual_handoff)
                task.source_payload = merge_agent_payload(
                    task.source_payload,
                    {
                        "manual_handoff": manual_handoff,
                        "alert": alert_payload,
                    },
                )
                await db.commit()
                deduped = await _should_dedupe_alert(db, task, alert_payload, manual_handoff)
                delivered = False
                if not deduped:
                    delivered = await send_pr_alert(
                        _build_alert_payload(task=task, repo=repo, alert=alert_payload, manual_handoff=manual_handoff)
                    )
                task.source_payload = merge_agent_payload(
                    task.source_payload,
                    {
                        "alert_delivery": {
                            "attempted": True,
                            "delivered": delivered,
                            "deduped": deduped,
                            "signature": dedupe_signature,
                        }
                    },
                )
                await db.commit()
            logger.info(
                "Agent task finished: task_id=%s status=%s failed_count=%s plan=%s tools=%s",
                task.id,
                final_status,
                failed_count,
                state.plan.pr_type,
                [item.name for item in state.tool_calls],
            )
        except Exception as exc:
            logger.exception("Agent task failed: task_id=%s", task.id)
            error_category = classify_pr_agent_error(exc)
            recovery_strategy = recovery_strategy_for(error_category)
            task.status = "failed"
            task.error_message = _build_error_message(error_category, str(exc))
            failure_message = f"生成失败：{exc}"
            if not _is_generation_completed(task.review_content):
                task.review_content = failure_message
            if not _is_generation_completed(task.test_suggestion_content):
                task.test_suggestion_content = failure_message
            if not _is_generation_completed(task.unit_test_generation_content):
                task.unit_test_generation_content = failure_message
            manual_handoff = _failure_manual_handoff(error_category, str(exc))
            alert_payload = {
                "required": manual_handoff is not None,
                "channel": "task_detail",
                "summary": str(exc)[:160],
            }
            dedupe_signature = _alert_signature(task, alert_payload, manual_handoff)
            task.source_payload = merge_agent_payload(
                task.source_payload,
                {
                    "mode": "pr_review_agent",
                    "failure_category": error_category,
                    "failure_message": str(exc),
                    "recovery": recovery_strategy["action"],
                    "recovery_description": recovery_strategy["description"],
                    "fallback": "filled_missing_stage_outputs",
                    "manual_handoff": manual_handoff,
                    "alert": alert_payload,
                },
            )
            delivered = False
            deduped = False
            if alert_payload["required"]:
                deduped = await _should_dedupe_alert(db, task, alert_payload, manual_handoff)
                if not deduped:
                    delivered = await send_pr_alert(
                        _build_alert_payload(task=task, repo=repo, alert=alert_payload, manual_handoff=manual_handoff)
                    )
            task.source_payload = merge_agent_payload(
                task.source_payload,
                {
                    "alert_delivery": {
                        "attempted": alert_payload["required"],
                        "delivered": delivered,
                        "deduped": deduped,
                        "signature": dedupe_signature,
                    }
                },
            )
            await db.commit()


async def list_user_tasks(user_id: str, db):
    result = await db.execute(select(AgentTask).where(AgentTask.user_id == user_id).order_by(AgentTask.created_at.desc(), AgentTask.id.desc()))
    return result.scalars().all()
