from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    from config import settings

    parser = argparse.ArgumentParser(description="Run offline RAG evaluation.")
    parser.add_argument("--dataset", required=True, help="Path to evaluation dataset JSON.")
    parser.add_argument("--output", default="backend/evaluation/output/report.json", help="Path to save evaluation report JSON.")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K chunks used for retrieval evaluation.")
    parser.add_argument("--use-ragas", action="store_true", help="Enable optional RAGAs scoring if dependency is installed.")
    parser.add_argument("--use-llm-judge", action="store_true", help="Enable LLM-as-a-judge scoring.")
    parser.add_argument("--judge-model", default=settings.chat_model, help="Judge model name.")
    parser.add_argument("--generation-model", default=settings.chat_model, help="Generation model name.")
    return parser


def main() -> None:
    from .runner import EvaluationOptions, run_from_cli

    args = build_parser().parse_args()
    report = run_from_cli(
        EvaluationOptions(
            dataset_path=args.dataset,
            output_path=args.output,
            top_k=args.top_k,
            use_ragas=args.use_ragas,
            use_llm_judge=args.use_llm_judge,
            judge_model=args.judge_model,
            generation_model=args.generation_model,
        )
    )
    print(
        f"Evaluation finished: samples={report.summary.sample_count} "
        f"recall@5={report.summary.retrieval.recall_at_5:.3f} "
        f"precision@5={report.summary.retrieval.precision_at_5:.3f}"
    )


if __name__ == "__main__":
    main()
