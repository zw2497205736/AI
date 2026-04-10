import logging

from sqlalchemy import select

from database import SessionLocal
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from services.pr_review_agent_service import run_pr_review_agent

logger = logging.getLogger(__name__)


async def _commit_stage(db, task: AgentTask, *, status: str, error_message: str | None = None):
    task.status = status
    task.error_message = error_message
    await db.commit()


def _is_generation_failed(content: str | None) -> bool:
    return bool(content and content.startswith("生成失败："))


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
            task.review_content = ""
            task.test_suggestion_content = ""
            task.unit_test_generation_content = ""
            await _commit_stage(db, task, status="running_review")

            state = await run_pr_review_agent(task, repo, db)
            if task.review_content:
                await _commit_stage(db, task, status="running_test_suggestion")
            if task.test_suggestion_content:
                await _commit_stage(db, task, status="running_unit_test_generation")

            failed_count = sum(
                [
                    _is_generation_failed(task.review_content),
                    _is_generation_failed(task.test_suggestion_content),
                    _is_generation_failed(task.unit_test_generation_content),
                ]
            )
            final_status = "partial_completed" if failed_count else "completed"
            final_error = f"{failed_count} 个阶段生成失败" if failed_count else None
            await _commit_stage(db, task, status=final_status, error_message=final_error)
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
            task.status = "failed"
            task.error_message = str(exc)
            failure_message = f"生成失败：{exc}"
            if not task.review_content:
                task.review_content = failure_message
            if not task.test_suggestion_content:
                task.test_suggestion_content = failure_message
            if not task.unit_test_generation_content:
                task.unit_test_generation_content = failure_message
            await db.commit()


async def list_user_tasks(user_id: str, db):
    result = await db.execute(select(AgentTask).where(AgentTask.user_id == user_id).order_by(AgentTask.created_at.desc(), AgentTask.id.desc()))
    return result.scalars().all()
