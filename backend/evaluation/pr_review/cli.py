from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    from config import settings

    parser = argparse.ArgumentParser(description="Run offline PR review evaluation.")
    parser.add_argument("--dataset", required=True, help="Path to PR review evaluation dataset JSON.")
    parser.add_argument("--output", default="backend/evaluation/output/pr_review_report.json", help="Path to save evaluation report JSON.")
    parser.add_argument("--markdown-output", default="", help="Optional path to save evaluation markdown report.")
    parser.add_argument("--mode", default="stage_only", choices=["stage_only", "full_agent"], help="Execution mode.")
    parser.add_argument("--generation-model", default=settings.pr_agent_generation_model, help="Generation model name.")
    parser.add_argument("--control-model", default=settings.pr_agent_control_model, help="Control model name.")
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM judge for review/test/unit stages.")
    parser.add_argument("--judge-model", default=settings.pr_agent_control_model, help="Judge model name.")
    parser.add_argument("--print-samples", type=int, default=5, help="How many sample summaries to print.")
    return parser


def main() -> None:
    from .runner import PRReviewEvaluationOptions, format_console_summary, run_pr_review_from_cli, write_markdown_report

    args = build_parser().parse_args()
    report = run_pr_review_from_cli(
        PRReviewEvaluationOptions(
            dataset_path=args.dataset,
            output_path=args.output,
            execution_mode=args.mode,
            generation_model=args.generation_model,
            control_model=args.control_model,
            use_llm_judge=args.use_llm_judge,
            judge_model=args.judge_model,
        )
    )
    if args.markdown_output:
        write_markdown_report(report, args.markdown_output, max_samples=args.print_samples)
    print(format_console_summary(report, max_samples=args.print_samples))


if __name__ == "__main__":
    main()
