from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    from config import settings

    parser = argparse.ArgumentParser(description="Compare two offline PR review evaluation configurations.")
    parser.add_argument("--dataset", required=True, help="Path to PR review evaluation dataset JSON.")
    parser.add_argument("--output", default="backend/evaluation/output/pr_review_compare.json", help="Path to save comparison JSON.")
    parser.add_argument("--markdown-output", default="", help="Optional path to save comparison markdown report.")
    parser.add_argument("--baseline-label", default="baseline", help="Baseline label.")
    parser.add_argument("--candidate-label", default="candidate", help="Candidate label.")
    parser.add_argument("--baseline-mode", default="stage_only", choices=["stage_only", "full_agent"], help="Baseline execution mode.")
    parser.add_argument("--candidate-mode", default="full_agent", choices=["stage_only", "full_agent"], help="Candidate execution mode.")
    parser.add_argument("--baseline-generation-model", default=settings.pr_agent_generation_model, help="Baseline generation model.")
    parser.add_argument("--candidate-generation-model", default=settings.pr_agent_generation_model, help="Candidate generation model.")
    parser.add_argument("--baseline-control-model", default=settings.pr_agent_control_model, help="Baseline control model.")
    parser.add_argument("--candidate-control-model", default=settings.pr_agent_control_model, help="Candidate control model.")
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM judge for both sides.")
    parser.add_argument("--baseline-judge-model", default=settings.pr_agent_control_model, help="Baseline judge model.")
    parser.add_argument("--candidate-judge-model", default=settings.pr_agent_control_model, help="Candidate judge model.")
    parser.add_argument("--print-samples", type=int, default=5, help="How many sample deltas to include in markdown report.")
    return parser


def main() -> None:
    from .runner import (
        PRReviewEvaluationOptions,
        format_comparison_markdown_report,
        run_pr_review_compare_from_cli,
        write_comparison_markdown_report,
    )

    args = build_parser().parse_args()
    report = run_pr_review_compare_from_cli(
        PRReviewEvaluationOptions(
            dataset_path=args.dataset,
            output_path="",
            execution_mode=args.baseline_mode,
            generation_model=args.baseline_generation_model,
            control_model=args.baseline_control_model,
            use_llm_judge=args.use_llm_judge,
            judge_model=args.baseline_judge_model,
        ),
        PRReviewEvaluationOptions(
            dataset_path=args.dataset,
            output_path="",
            execution_mode=args.candidate_mode,
            generation_model=args.candidate_generation_model,
            control_model=args.candidate_control_model,
            use_llm_judge=args.use_llm_judge,
            judge_model=args.candidate_judge_model,
        ),
        baseline_label=args.baseline_label,
        candidate_label=args.candidate_label,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        write_comparison_markdown_report(report, args.markdown_output, max_samples=args.print_samples)
    print(format_comparison_markdown_report(report, max_samples=args.print_samples))


if __name__ == "__main__":
    main()
