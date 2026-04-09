import asyncio
import logging
from typing import Any
from sqlalchemy import select

from config import settings
from database import SessionLocal
from models.agent_task import AgentTask
from models.github_repository import GitHubRepository
from prompts.github_pr_review import REVIEW_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT_COMPACT
from prompts.github_pr_testing import UNIT_TEST_GENERATION_PROMPT, UNIT_TEST_GENERATION_PROMPT_COMPACT
from services.github_service import build_reviewable_diff, fetch_pull_request, fetch_pull_request_files
from services.llm_service import create_text_response

logger = logging.getLogger(__name__)


async def _run_markdown_completion(system_prompt: str, user_prompt: str) -> str:
    return await create_text_response(
        model=settings.chat_model,
        instructions=system_prompt,
        input_messages=[{"role": "user", "content": user_prompt}],
        temperature=0.2,
        max_output_tokens=1600,
    )


async def _safe_run_markdown_completion(system_prompt: str, user_prompt: str, fallback_prompt: str | None = None) -> str:
    attempts = max(1, settings.llm_retry_attempts)
    last_exc: Exception | None = None
    prompt_candidates = [system_prompt]
    if fallback_prompt:
        prompt_candidates.append(fallback_prompt)
    for prompt_index, prompt in enumerate(prompt_candidates, start=1):
        for attempt in range(1, attempts + 1):
            try:
                logger.info("Agent stage request started: prompt_variant=%s attempt=%s", prompt_index, attempt)
                content = await _run_markdown_completion(prompt, user_prompt)
                logger.info("Agent stage request completed: prompt_variant=%s attempt=%s", prompt_index, attempt)
                return content.strip() or "暂无结果"
            except Exception as exc:
                last_exc = exc
                logger.exception("Agent stage request failed: prompt_variant=%s attempt=%s", prompt_index, attempt)
                if attempt < attempts:
                    await asyncio.sleep(min(2 * attempt, 4))
    return f"生成失败：{last_exc}"


async def _commit_stage(db, task: AgentTask, *, status: str, error_message: str | None = None):
    task.status = status
    task.error_message = error_message
    await db.commit()


def _is_generation_failed(content: str | None) -> bool:
    return bool(content and content.startswith("生成失败："))


def _build_user_prompt(repo: GitHubRepository, pr_data: dict[str, Any], diff_text: str) -> str:
    return (
        f"仓库：{repo.repo_owner}/{repo.repo_name}\n"
        f"PR 标题：{pr_data.get('title', '')}\n"
        f"PR 描述：{pr_data.get('body') or '无'}\n"
        f"目标分支：{pr_data.get('base', {}).get('ref', '')}\n"
        f"来源分支：{pr_data.get('head', {}).get('ref', '')}\n"
        f"变更 diff：\n\n{diff_text}"
    )


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
            pr_data = await fetch_pull_request(repo, task.pr_number or 0)
            files = await fetch_pull_request_files(repo, task.pr_number or 0)
            diff_text = build_reviewable_diff(files)
            if not diff_text.strip():
                raise ValueError("No reviewable diff content fetched from GitHub")

            user_prompt = _build_user_prompt(repo, pr_data, diff_text)
            task.title = pr_data.get("title") or task.title
            task.commit_sha = pr_data.get("head", {}).get("sha") or task.commit_sha
            task.review_content = ""
            task.test_suggestion_content = ""
            task.unit_test_generation_content = ""
            await _commit_stage(db, task, status="running_review")
            logger.info("Agent task stage: task_id=%s stage=running_review", task.id)

            review_content = await _safe_run_markdown_completion(REVIEW_SYSTEM_PROMPT, user_prompt)
            task.review_content = review_content
            await _commit_stage(db, task, status="running_test_suggestion")
            logger.info("Agent task stage: task_id=%s stage=running_test_suggestion", task.id)

            test_suggestion_content = await _safe_run_markdown_completion(TEST_SYSTEM_PROMPT, user_prompt, TEST_SYSTEM_PROMPT_COMPACT)
            task.test_suggestion_content = test_suggestion_content
            await _commit_stage(db, task, status="running_unit_test_generation")
            logger.info("Agent task stage: task_id=%s stage=running_unit_test_generation", task.id)

            unit_test_generation_content = await _safe_run_markdown_completion(
                UNIT_TEST_GENERATION_PROMPT, user_prompt, UNIT_TEST_GENERATION_PROMPT_COMPACT
            )
            task.unit_test_generation_content = unit_test_generation_content
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
            logger.info("Agent task finished: task_id=%s status=%s failed_count=%s", task.id, final_status, failed_count)
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
