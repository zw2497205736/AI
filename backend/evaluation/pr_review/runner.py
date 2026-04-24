from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .dataset_loader import load_pr_review_dataset
from .judges import average_stage_judges, judge_review_stage, judge_test_stage, judge_unit_test_stage
from .metrics import (
    average_cross_stage_metrics,
    average_review_metrics,
    average_test_metrics,
    average_unit_test_metrics,
    diagnose_cross_stage,
    diagnose_review_output,
    diagnose_test_output,
    diagnose_unit_test_output,
    evaluate_cross_stage,
    evaluate_review_output,
    evaluate_test_output,
    evaluate_unit_test_output,
)
from .schemas import (
    ExecutionMode,
    PRReviewComparisonReport,
    PRReviewComparisonSampleDelta,
    PRReviewEvaluationReport,
    PRReviewEvaluationSummary,
    PRReviewSampleEvaluationResult,
    PRReviewStageOutputs,
)


@dataclass
class PRReviewEvaluationOptions:
    dataset_path: str
    output_path: str
    execution_mode: ExecutionMode = "stage_only"
    generation_model: str = ""
    control_model: str = ""
    use_llm_judge: bool = False
    judge_model: str = ""


async def run_pr_review_evaluation(options: PRReviewEvaluationOptions) -> PRReviewEvaluationReport:
    dataset = load_pr_review_dataset(options.dataset_path)
    results: list[PRReviewSampleEvaluationResult] = []
    with _temporary_model_settings(options):
        for sample in dataset.samples:
            outputs, trace_metadata = await _run_sample(sample, options.execution_mode)
            review_metrics = evaluate_review_output(
                outputs.review_content,
                sample.ground_truth.must_find_issues,
                sample.ground_truth.merge_recommendation,
            )
            review_diagnostics = diagnose_review_output(
                outputs.review_content,
                sample.ground_truth.must_find_issues,
                sample.ground_truth.merge_recommendation,
            )
            test_metrics = evaluate_test_output(outputs.test_suggestion_content, sample.ground_truth.test_focuses)
            test_diagnostics = diagnose_test_output(outputs.test_suggestion_content, sample.ground_truth.test_focuses)
            unit_test_metrics = evaluate_unit_test_output(outputs.unit_test_generation_content, sample.ground_truth.unit_test_targets)
            unit_test_diagnostics = diagnose_unit_test_output(outputs.unit_test_generation_content, sample.ground_truth.unit_test_targets)
            cross_stage_metrics = evaluate_cross_stage(outputs)
            cross_stage_diagnostics = diagnose_cross_stage(outputs)
            review_judge, test_judge, unit_test_judge = await _judge_sample(sample, outputs, options)
            results.append(
                PRReviewSampleEvaluationResult(
                    sample_id=sample.sample_id,
                    outputs=outputs,
                    review_metrics=review_metrics,
                    review_judge=review_judge,
                    review_diagnostics=review_diagnostics,
                    test_metrics=test_metrics,
                    test_judge=test_judge,
                    test_diagnostics=test_diagnostics,
                    unit_test_metrics=unit_test_metrics,
                    unit_test_judge=unit_test_judge,
                    unit_test_diagnostics=unit_test_diagnostics,
                    cross_stage_metrics=cross_stage_metrics,
                    cross_stage_diagnostics=cross_stage_diagnostics,
                    metadata={
                        "repo_name": sample.repo_name,
                        "pr_number": sample.pr_number,
                        "pr_type": sample.metadata.get("pr_type"),
                        "language": sample.metadata.get("language"),
                        **trace_metadata,
                    },
                )
            )

    summary = PRReviewEvaluationSummary(
        dataset_name=dataset.dataset_name,
        dataset_version=dataset.version,
        sample_count=len(results),
        execution_mode=options.execution_mode,
        review_metrics=average_review_metrics(item.review_metrics for item in results),
        review_judge=average_stage_judges([item.review_judge for item in results]),
        test_metrics=average_test_metrics(item.test_metrics for item in results),
        test_judge=average_stage_judges([item.test_judge for item in results]),
        unit_test_metrics=average_unit_test_metrics(item.unit_test_metrics for item in results),
        unit_test_judge=average_stage_judges([item.unit_test_judge for item in results]),
        cross_stage_metrics=average_cross_stage_metrics(item.cross_stage_metrics for item in results),
        metadata={
            "generation_model": options.generation_model,
            "control_model": options.control_model,
            "use_llm_judge": options.use_llm_judge,
            "judge_model": options.judge_model,
        },
    )
    report = PRReviewEvaluationReport(summary=summary, samples=results)
    _write_report(report, options.output_path)
    return report


def format_markdown_report(report: PRReviewEvaluationReport, *, max_samples: int | None = None) -> str:
    summary = report.summary
    samples = report.samples if max_samples is None else report.samples[:max_samples]
    lines: list[str] = [
        "# PR Review Evaluation Report",
        "",
        "## Summary",
        f"- Dataset: `{summary.dataset_name}` / `{summary.dataset_version}`",
        f"- Samples: `{summary.sample_count}`",
        f"- Mode: `{summary.execution_mode}`",
        "",
        "### Review Metrics",
        f"- `must_find_recall`: `{summary.review_metrics.must_find_recall:.3f}`",
        f"- `precision_hint`: `{summary.review_metrics.precision_hint:.3f}`",
        f"- `specificity_score`: `{summary.review_metrics.specificity_score:.3f}`",
        f"- `vagueness_score`: `{summary.review_metrics.vagueness_score:.3f}`",
        f"- `merge_judgement_match`: `{summary.review_metrics.merge_judgement_match:.3f}`",
        f"- `judge_score`: `{_format_optional_float(summary.review_judge.judge_score)}`",
        "",
        "### Test Metrics",
        f"- `test_focus_coverage`: `{summary.test_metrics.test_focus_coverage:.3f}`",
        f"- `actionability_score`: `{summary.test_metrics.actionability_score:.3f}`",
        f"- `risk_regression_coverage`: `{summary.test_metrics.risk_regression_coverage:.3f}`",
        f"- `vagueness_score`: `{summary.test_metrics.vagueness_score:.3f}`",
        f"- `judge_score`: `{_format_optional_float(summary.test_judge.judge_score)}`",
        "",
        "### Unit Test Metrics",
        f"- `target_alignment`: `{summary.unit_test_metrics.target_alignment:.3f}`",
        f"- `mock_awareness`: `{summary.unit_test_metrics.mock_awareness:.3f}`",
        f"- `skeleton_presence`: `{summary.unit_test_metrics.skeleton_presence:.3f}`",
        f"- `assertion_quality`: `{summary.unit_test_metrics.assertion_quality:.3f}`",
        f"- `vagueness_score`: `{summary.unit_test_metrics.vagueness_score:.3f}`",
        f"- `judge_score`: `{_format_optional_float(summary.unit_test_judge.judge_score)}`",
        "",
        "### Cross Stage Metrics",
        f"- `format_stability`: `{summary.cross_stage_metrics.format_stability:.3f}`",
        f"- `empty_output`: `{summary.cross_stage_metrics.empty_output:.3f}`",
        f"- `failed_output`: `{summary.cross_stage_metrics.failed_output:.3f}`",
        "",
        "## Samples",
    ]

    for sample in samples:
        lines.extend(
            [
                "",
                f"### {sample.sample_id}",
                f"- Repo: `{sample.metadata.get('repo_name', 'unknown/repo')}`",
                f"- PR Type: `{sample.metadata.get('pr_type', 'unknown')}`",
                f"- Language: `{sample.metadata.get('language', 'unknown')}`",
                "",
                "**Scores**",
                f"- Review: recall=`{sample.review_metrics.must_find_recall:.2f}` precision=`{sample.review_metrics.precision_hint:.2f}` specificity=`{sample.review_metrics.specificity_score:.2f}` vagueness=`{sample.review_metrics.vagueness_score:.2f}` judge=`{_format_optional_float(sample.review_judge.judge_score)}`",
                f"- Test: coverage=`{sample.test_metrics.test_focus_coverage:.2f}` actionability=`{sample.test_metrics.actionability_score:.2f}` vagueness=`{sample.test_metrics.vagueness_score:.2f}` judge=`{_format_optional_float(sample.test_judge.judge_score)}`",
                f"- Unit Test: alignment=`{sample.unit_test_metrics.target_alignment:.2f}` skeleton=`{sample.unit_test_metrics.skeleton_presence:.2f}` vagueness=`{sample.unit_test_metrics.vagueness_score:.2f}` judge=`{_format_optional_float(sample.unit_test_judge.judge_score)}`",
                f"- Cross Stage: failed=`{sample.cross_stage_metrics.failed_output:.2f}` empty=`{sample.cross_stage_metrics.empty_output:.2f}`",
                "",
                "**Diagnostics**",
                f"- Matched issues: {_format_list(sample.review_diagnostics.matched_issue_titles)}",
                f"- Missed issues: {_format_list(sample.review_diagnostics.missed_issue_titles)}",
                f"- Covered test focuses: {_format_list(sample.test_diagnostics.covered_focuses)}",
                f"- Missed test focuses: {_format_list(sample.test_diagnostics.missed_focuses)}",
                f"- Matched unit targets: {_format_list(sample.unit_test_diagnostics.matched_targets)}",
                f"- Missed unit targets: {_format_list(sample.unit_test_diagnostics.missed_targets)}",
                f"- Empty stages: {_format_list(sample.cross_stage_diagnostics.empty_stages)}",
                f"- Failed stages: {_format_list(sample.cross_stage_diagnostics.failed_stages)}",
                f"- Review judge: {_format_optional_text(sample.review_judge.judge_reason)}",
                f"- Test judge: {_format_optional_text(sample.test_judge.judge_reason)}",
                f"- Unit judge: {_format_optional_text(sample.unit_test_judge.judge_reason)}",
            ]
        )

        lines.extend(
            [
                "",
                "**Output Preview**",
                "",
                "#### Review",
                "",
                _trim_markdown_block(sample.outputs.review_content),
                "",
                "#### Test Suggestion",
                "",
                _trim_markdown_block(sample.outputs.test_suggestion_content),
                "",
                "#### Unit Test",
                "",
                _trim_markdown_block(sample.outputs.unit_test_generation_content),
            ]
        )

    return "\n".join(lines).strip() + "\n"


def format_comparison_markdown_report(report: PRReviewComparisonReport, *, max_samples: int | None = None) -> str:
    samples = report.sample_deltas if max_samples is None else report.sample_deltas[:max_samples]
    lines = [
        "# PR Review Comparison Report",
        "",
        f"- Baseline: `{report.baseline_label}`",
        f"- Candidate: `{report.candidate_label}`",
        "",
        "## Metric Deltas",
    ]
    for key, value in sorted(report.metric_deltas.items()):
        lines.append(f"- `{key}`: `{_format_optional_float(value)}`")
    lines.extend(["", "## Sample Deltas"])
    for sample in samples:
        lines.extend(
            [
                "",
                f"### {sample.sample_id}",
                f"- `review_recall_delta`: `{sample.review_recall_delta:.3f}`",
                f"- `review_precision_delta`: `{sample.review_precision_delta:.3f}`",
                f"- `review_vagueness_delta`: `{sample.review_vagueness_delta:.3f}`",
                f"- `test_coverage_delta`: `{sample.test_coverage_delta:.3f}`",
                f"- `test_vagueness_delta`: `{sample.test_vagueness_delta:.3f}`",
                f"- `unit_alignment_delta`: `{sample.unit_alignment_delta:.3f}`",
                f"- `unit_vagueness_delta`: `{sample.unit_vagueness_delta:.3f}`",
                f"- `review_judge_delta`: `{_format_optional_float(sample.review_judge_delta)}`",
                f"- `test_judge_delta`: `{_format_optional_float(sample.test_judge_delta)}`",
                f"- `unit_judge_delta`: `{_format_optional_float(sample.unit_judge_delta)}`",
                f"- `regression_flags`: `{_format_list(sample.regression_flags)}`",
            ]
        )
    return "\n".join(lines).strip() + "\n"


async def _run_sample(sample, execution_mode: ExecutionMode) -> tuple[PRReviewStageOutputs, dict]:
    if execution_mode == "full_agent":
        return await _run_full_agent_offline(sample)
    return await _run_stage_only(sample)


async def _run_stage_only(sample) -> tuple[PRReviewStageOutputs, dict]:
    from services.pr_review_agent_service import AgentPlan, PRReviewAgentState, _generate_stage

    state = PRReviewAgentState(
        task_id=0,
        repo_id=0,
        pr_number=sample.pr_number or 0,
        repo_full_name=sample.repo_name,
        pr_title=sample.title,
        pr_body=sample.body,
        diff_text=sample.diff_text,
        changed_files=[item.filename for item in sample.changed_files],
        plan=AgentPlan(
            pr_type=str(sample.metadata.get("pr_type") or "other"),
            focus=[],
            steps=[],
            knowledge_queries=[],
            suggested_tools=[],
            planning_note="offline_evaluation_stage_only",
        ),
    )
    await _generate_stage(state, "review")
    await _generate_stage(state, "test_suggestion")
    await _generate_stage(state, "unit_test")
    return _outputs_from_state(state), {
        "execution_mode": "stage_only",
        "executed_steps": state.executed_steps,
        "tool_calls": [],
        "replans": [],
        "fallback_events": state.fallback_events,
    }


async def _run_full_agent_offline(sample) -> tuple[PRReviewStageOutputs, dict]:
    from services.pr_review_agent_service import (
        AgentToolRecord,
        PRReviewAgentState,
        _build_execution_summary,
        _decide_next_action,
        _generate_stage,
        _plan_agent,
        _replan_agent,
    )

    files = [item.model_dump() for item in sample.changed_files]
    repo_owner, repo_name = _split_repo_name(sample.repo_name)
    repo = SimpleNamespace(id=0, repo_owner=repo_owner, repo_name=repo_name)
    pr_data = {
        "title": sample.title,
        "body": sample.body,
        "base": {"ref": sample.metadata.get("base_ref", "main")},
        "head": {"ref": sample.metadata.get("head_ref", "feature/eval")},
    }
    state = PRReviewAgentState(
        task_id=0,
        repo_id=0,
        pr_number=sample.pr_number or 0,
        repo_full_name=sample.repo_name,
        pr_title=sample.title,
        pr_body=sample.body,
        diff_text=sample.diff_text,
        changed_files=[item.filename for item in sample.changed_files],
    )
    state.plan = await _plan_agent(repo, pr_data, files, sample.diff_text)

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
            await _replan_agent(state, "offline_agent_progress_stagnant")
            stagnant_rounds = 0

        action = await _decide_next_action(state)
        action_type = str(action.get("action") or "").strip()
        if action_type == "use_tool":
            await _offline_execute_tool(state, sample, str(action.get("tool_name") or ""), action.get("arguments") or {})
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
                    await _replan_agent(state, f"offline_{stage}_generation_failed")
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
        state.fallback_events.append("offline_force_generate_review_after_loop")
        await _generate_stage(state, "review")
    if not state.test_suggestion_content:
        state.fallback_events.append("offline_force_generate_test_suggestion_after_loop")
        await _generate_stage(state, "test_suggestion")
    if not state.unit_test_generation_content:
        state.fallback_events.append("offline_force_generate_unit_test_after_loop")
        await _generate_stage(state, "unit_test")

    state.execution_summary = await _build_execution_summary(state)
    return _outputs_from_state(state), {
        "execution_mode": "full_agent",
        "plan": state.plan.__dict__,
        "executed_steps": state.executed_steps,
        "tool_calls": [{"name": item.name, "arguments": item.arguments} for item in state.tool_calls],
        "replans": state.replans,
        "fallback_events": state.fallback_events,
        "execution_summary": state.execution_summary,
    }


async def _offline_execute_tool(state, sample, tool_name: str, arguments: dict) -> None:
    from services.pr_review_agent_service import AgentToolRecord
    from services.pr_review_tool_service import build_pr_diff_tool_result, build_pr_meta_tool_result

    arguments = arguments if isinstance(arguments, dict) else {}
    if any(item.name == tool_name and item.arguments == arguments for item in state.tool_calls):
        return

    files = [item.model_dump() for item in sample.changed_files]
    repo_owner, repo_name = _split_repo_name(sample.repo_name)
    repo = SimpleNamespace(repo_owner=repo_owner, repo_name=repo_name)
    pr_data = {
        "title": sample.title,
        "body": sample.body,
        "base": {"ref": sample.metadata.get("base_ref", "main")},
        "head": {"ref": sample.metadata.get("head_ref", "feature/eval")},
    }

    if tool_name == "get_pr_meta":
        output = build_pr_meta_tool_result(repo, pr_data, files)
    elif tool_name == "get_pr_diff":
        output = build_pr_diff_tool_result(sample.diff_text)
    elif tool_name == "search_review_knowledge":
        query = str(arguments.get("query") or "")
        knowledge_snippets = sample.metadata.get("knowledge_snippets") or []
        if knowledge_snippets:
            state.knowledge_sources.extend(
                [{"filename": item.get("filename", "offline-knowledge"), "content": item.get("content", ""), "source_type": "offline_eval"} for item in knowledge_snippets]
            )
            output = "\n\n".join(
                f"[{index}] 来源：{item.get('filename', 'offline-knowledge')}\n{item.get('content', '')[:500]}"
                for index, item in enumerate(knowledge_snippets, start=1)
            )
        else:
            output = f"未命中离线知识样本。query={query}"
    else:
        output = "离线评测模式下无历史任务上下文。"

    state.tool_calls.append(AgentToolRecord(name=tool_name, arguments=arguments, output_preview=_truncate_output(output, 280)))
    state.executed_steps.append(f"tool:{tool_name}")


def _outputs_from_state(state) -> PRReviewStageOutputs:
    return PRReviewStageOutputs(
        review_content=state.review_content,
        test_suggestion_content=state.test_suggestion_content,
        unit_test_generation_content=state.unit_test_generation_content,
    )


def format_console_summary(report: PRReviewEvaluationReport, *, max_samples: int = 5) -> str:
    summary = report.summary
    lines = [
        f"PR review evaluation finished: samples={summary.sample_count} mode={summary.execution_mode}",
        (
            "summary "
            f"must_find_recall={summary.review_metrics.must_find_recall:.3f} "
            f"precision_hint={summary.review_metrics.precision_hint:.3f} "
            f"review_judge={_format_optional_float(summary.review_judge.judge_score)} "
            f"specificity={summary.review_metrics.specificity_score:.3f} "
            f"review_vagueness={summary.review_metrics.vagueness_score:.3f} "
            f"test_focus_coverage={summary.test_metrics.test_focus_coverage:.3f} "
            f"test_judge={_format_optional_float(summary.test_judge.judge_score)} "
            f"test_vagueness={summary.test_metrics.vagueness_score:.3f} "
            f"target_alignment={summary.unit_test_metrics.target_alignment:.3f} "
            f"unit_judge={_format_optional_float(summary.unit_test_judge.judge_score)} "
            f"unit_vagueness={summary.unit_test_metrics.vagueness_score:.3f} "
            f"failed_output={summary.cross_stage_metrics.failed_output:.3f}"
        ),
    ]
    for sample in report.samples[:max_samples]:
        lines.append(
            (
                f"- {sample.sample_id} "
                f"review={sample.review_metrics.must_find_recall:.2f} "
                f"review_judge={_format_optional_float(sample.review_judge.judge_score)} "
                f"precision={sample.review_metrics.precision_hint:.2f} "
                f"review_vague={sample.review_metrics.vagueness_score:.2f} "
                f"test={sample.test_metrics.test_focus_coverage:.2f} "
                f"test_judge={_format_optional_float(sample.test_judge.judge_score)} "
                f"test_vague={sample.test_metrics.vagueness_score:.2f} "
                f"unit={sample.unit_test_metrics.target_alignment:.2f} "
                f"unit_judge={_format_optional_float(sample.unit_test_judge.judge_score)} "
                f"unit_vague={sample.unit_test_metrics.vagueness_score:.2f} "
                f"failed={sample.cross_stage_metrics.failed_output:.2f}"
            )
        )
        if sample.review_diagnostics.missed_issue_titles:
            lines.append(f"  missed_issues={'; '.join(sample.review_diagnostics.missed_issue_titles[:3])}")
        if sample.test_diagnostics.missed_focuses:
            lines.append(f"  missed_test_focuses={'; '.join(sample.test_diagnostics.missed_focuses[:3])}")
        if sample.unit_test_diagnostics.missed_targets:
            lines.append(f"  missed_unit_targets={'; '.join(sample.unit_test_diagnostics.missed_targets[:3])}")
    return "\n".join(lines)


def _split_repo_name(repo_name: str) -> tuple[str, str]:
    if "/" in repo_name:
        owner, name = repo_name.split("/", 1)
        return owner, name
    return "offline", repo_name


def _truncate_output(text: str, limit: int = 280) -> str:
    normalized = (text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "\n...[truncated]"


def _write_report(report: PRReviewEvaluationReport, output_path: str) -> None:
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_report(report: PRReviewEvaluationReport, output_path: str, *, max_samples: int | None = None) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_markdown_report(report, max_samples=max_samples), encoding="utf-8")


def write_comparison_markdown_report(report: PRReviewComparisonReport, output_path: str, *, max_samples: int | None = None) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_comparison_markdown_report(report, max_samples=max_samples), encoding="utf-8")


def run_pr_review_from_cli(options: PRReviewEvaluationOptions) -> PRReviewEvaluationReport:
    return asyncio.run(run_pr_review_evaluation(options))


async def compare_pr_review_evaluations(
    baseline: PRReviewEvaluationOptions,
    candidate: PRReviewEvaluationOptions,
    *,
    baseline_label: str,
    candidate_label: str,
) -> PRReviewComparisonReport:
    baseline_report = await run_pr_review_evaluation(baseline)
    candidate_report = await run_pr_review_evaluation(candidate)
    return _build_comparison_report(
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
    )


def run_pr_review_compare_from_cli(
    baseline: PRReviewEvaluationOptions,
    candidate: PRReviewEvaluationOptions,
    *,
    baseline_label: str,
    candidate_label: str,
) -> PRReviewComparisonReport:
    return asyncio.run(
        compare_pr_review_evaluations(
            baseline,
            candidate,
            baseline_label=baseline_label,
            candidate_label=candidate_label,
        )
    )


async def _judge_sample(sample, outputs: PRReviewStageOutputs, options: PRReviewEvaluationOptions):
    from .schemas import StageJudgeMetrics

    if not options.use_llm_judge:
        empty = StageJudgeMetrics()
        return empty, empty, empty

    judge_model = options.judge_model or options.generation_model
    review_judge = await judge_review_stage(
        model=judge_model,
        pr_title=sample.title,
        ground_truth={
            "must_find_issues": [item.model_dump() for item in sample.ground_truth.must_find_issues],
            "merge_recommendation": sample.ground_truth.merge_recommendation,
        },
        output=outputs.review_content,
    )
    test_judge = await judge_test_stage(
        model=judge_model,
        pr_title=sample.title,
        ground_truth={"test_focuses": sample.ground_truth.test_focuses},
        output=outputs.test_suggestion_content,
    )
    unit_test_judge = await judge_unit_test_stage(
        model=judge_model,
        pr_title=sample.title,
        ground_truth={"unit_test_targets": sample.ground_truth.unit_test_targets},
        output=outputs.unit_test_generation_content,
    )
    return review_judge, test_judge, unit_test_judge


def _format_list(values: list[str]) -> str:
    return "无" if not values else "；".join(values[:5])


def _trim_markdown_block(text: str, limit: int = 1200) -> str:
    content = (text or "").strip()
    if not content:
        return "_无输出_"
    if len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n\n...[truncated]"


def _format_optional_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _format_optional_text(value: str | None) -> str:
    return value or "无"


@contextmanager
def _temporary_model_settings(options: PRReviewEvaluationOptions):
    from config import settings

    original_generation = settings.pr_agent_generation_model
    original_control = settings.pr_agent_control_model
    try:
        if options.generation_model:
            settings.pr_agent_generation_model = options.generation_model
        if options.control_model:
            settings.pr_agent_control_model = options.control_model
        yield
    finally:
        settings.pr_agent_generation_model = original_generation
        settings.pr_agent_control_model = original_control


def _build_comparison_report(
    *,
    baseline_report: PRReviewEvaluationReport,
    candidate_report: PRReviewEvaluationReport,
    baseline_label: str,
    candidate_label: str,
) -> PRReviewComparisonReport:
    baseline_samples = {item.sample_id: item for item in baseline_report.samples}
    candidate_samples = {item.sample_id: item for item in candidate_report.samples}
    sample_ids = sorted(set(baseline_samples) & set(candidate_samples))
    sample_deltas: list[PRReviewComparisonSampleDelta] = []
    for sample_id in sample_ids:
        base = baseline_samples[sample_id]
        cand = candidate_samples[sample_id]
        regression_flags: list[str] = []
        if cand.review_metrics.must_find_recall < base.review_metrics.must_find_recall:
            regression_flags.append("review_recall_down")
        if cand.review_metrics.vagueness_score > base.review_metrics.vagueness_score:
            regression_flags.append("review_vagueness_up")
        if cand.test_metrics.test_focus_coverage < base.test_metrics.test_focus_coverage:
            regression_flags.append("test_coverage_down")
        if cand.unit_test_metrics.target_alignment < base.unit_test_metrics.target_alignment:
            regression_flags.append("unit_alignment_down")
        sample_deltas.append(
            PRReviewComparisonSampleDelta(
                sample_id=sample_id,
                review_recall_delta=cand.review_metrics.must_find_recall - base.review_metrics.must_find_recall,
                review_precision_delta=cand.review_metrics.precision_hint - base.review_metrics.precision_hint,
                review_vagueness_delta=cand.review_metrics.vagueness_score - base.review_metrics.vagueness_score,
                test_coverage_delta=cand.test_metrics.test_focus_coverage - base.test_metrics.test_focus_coverage,
                test_vagueness_delta=cand.test_metrics.vagueness_score - base.test_metrics.vagueness_score,
                unit_alignment_delta=cand.unit_test_metrics.target_alignment - base.unit_test_metrics.target_alignment,
                unit_vagueness_delta=cand.unit_test_metrics.vagueness_score - base.unit_test_metrics.vagueness_score,
                review_judge_delta=_optional_delta(cand.review_judge.judge_score, base.review_judge.judge_score),
                test_judge_delta=_optional_delta(cand.test_judge.judge_score, base.test_judge.judge_score),
                unit_judge_delta=_optional_delta(cand.unit_test_judge.judge_score, base.unit_test_judge.judge_score),
                regression_flags=regression_flags,
            )
        )

    return PRReviewComparisonReport(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        baseline_summary=baseline_report.summary,
        candidate_summary=candidate_report.summary,
        metric_deltas={
            "review.must_find_recall": candidate_report.summary.review_metrics.must_find_recall - baseline_report.summary.review_metrics.must_find_recall,
            "review.precision_hint": candidate_report.summary.review_metrics.precision_hint - baseline_report.summary.review_metrics.precision_hint,
            "review.specificity_score": candidate_report.summary.review_metrics.specificity_score - baseline_report.summary.review_metrics.specificity_score,
            "review.vagueness_score": candidate_report.summary.review_metrics.vagueness_score - baseline_report.summary.review_metrics.vagueness_score,
            "review.judge_score": _optional_delta(candidate_report.summary.review_judge.judge_score, baseline_report.summary.review_judge.judge_score),
            "test.test_focus_coverage": candidate_report.summary.test_metrics.test_focus_coverage - baseline_report.summary.test_metrics.test_focus_coverage,
            "test.vagueness_score": candidate_report.summary.test_metrics.vagueness_score - baseline_report.summary.test_metrics.vagueness_score,
            "test.judge_score": _optional_delta(candidate_report.summary.test_judge.judge_score, baseline_report.summary.test_judge.judge_score),
            "unit.target_alignment": candidate_report.summary.unit_test_metrics.target_alignment - baseline_report.summary.unit_test_metrics.target_alignment,
            "unit.vagueness_score": candidate_report.summary.unit_test_metrics.vagueness_score - baseline_report.summary.unit_test_metrics.vagueness_score,
            "unit.judge_score": _optional_delta(candidate_report.summary.unit_test_judge.judge_score, baseline_report.summary.unit_test_judge.judge_score),
            "cross.failed_output": candidate_report.summary.cross_stage_metrics.failed_output - baseline_report.summary.cross_stage_metrics.failed_output,
        },
        sample_deltas=sample_deltas,
    )


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline
