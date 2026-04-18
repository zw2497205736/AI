from __future__ import annotations

from .schemas import GenerationMetrics, RetrievedChunk


async def try_score_with_ragas(*, question: str, answer: str, contexts: list[RetrievedChunk], gold_answer: str) -> GenerationMetrics:
    """Best-effort RAGAs scoring.

    This function stays optional on purpose. If `ragas` is not installed,
    evaluation still works and simply returns empty metric fields.
    """

    try:
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_recall, faithfulness
        from datasets import Dataset
    except Exception:
        return GenerationMetrics()

    dataset = Dataset.from_dict(
        {
            "question": [question],
            "answer": [answer],
            "contexts": [[item.content for item in contexts]],
            "ground_truth": [gold_answer],
        }
    )

    result = evaluate(dataset=dataset, metrics=[faithfulness, answer_relevancy, context_recall])
    rows = result.to_pandas().to_dict(orient="records")
    first = rows[0] if rows else {}
    return GenerationMetrics(
        faithfulness=_safe_float(first.get("faithfulness")),
        answer_relevance=_safe_float(first.get("answer_relevancy")),
        context_relevance=_safe_float(first.get("context_recall")),
    )


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
