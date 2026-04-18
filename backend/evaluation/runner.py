from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from .dataset_loader import load_dataset
from .judges import judge_correctness, judge_generation
from .metrics import average_end_to_end_metrics, average_generation_metrics, average_retrieval_metrics, compute_retrieval_metrics, cosine_similarity
from .ragas_adapter import try_score_with_ragas
from .schemas import (
    EndToEndMetrics,
    EvaluationReport,
    EvaluationSummary,
    GenerationMetrics,
    RetrievedChunk,
    SampleEvaluationResult,
)


@dataclass
class EvaluationOptions:
    dataset_path: str
    output_path: str
    top_k: int = 5
    use_ragas: bool = False
    use_llm_judge: bool = False
    judge_model: str = ""
    generation_model: str = ""


async def run_evaluation(options: EvaluationOptions) -> EvaluationReport:
    from services.llm_service import get_chat_client, get_embedding_client
    from services.rag_service import filter_relevant_chunks, hybrid_retrieve

    dataset = load_dataset(options.dataset_path)
    embedding_client = get_embedding_client()
    chat_client = get_chat_client()

    results: list[SampleEvaluationResult] = []
    for sample in dataset.samples:
        retrieved = await hybrid_retrieve(sample.question, embedding_client)
        filtered = await filter_relevant_chunks(sample.question, retrieved, chat_client)
        contexts = [_to_retrieved_chunk(item) for item in filtered[: options.top_k]]
        retrieval_metrics = compute_retrieval_metrics(contexts, sample.gold_chunks, top_k=options.top_k)
        answer = await _generate_answer(
            question=sample.question,
            gold_answer=sample.gold_answer,
            contexts=contexts,
            generation_model=options.generation_model,
        )

        generation_metrics = GenerationMetrics()
        if options.use_ragas:
            generation_metrics = await try_score_with_ragas(
                question=sample.question,
                answer=answer,
                contexts=contexts,
                gold_answer=sample.gold_answer,
            )
        if options.use_llm_judge:
            judge_metrics = await judge_generation(
                model=options.judge_model or options.generation_model,
                question=sample.question,
                answer=answer,
                contexts=contexts,
            )
            generation_metrics = generation_metrics.model_copy(
                update={
                    "judge_score": judge_metrics.judge_score,
                    "judge_label": judge_metrics.judge_label,
                    "judge_reason": judge_metrics.judge_reason,
                    "faithfulness": judge_metrics.faithfulness if generation_metrics.faithfulness is None else generation_metrics.faithfulness,
                    "answer_relevance": judge_metrics.answer_relevance if generation_metrics.answer_relevance is None else generation_metrics.answer_relevance,
                    "context_relevance": judge_metrics.context_relevance if generation_metrics.context_relevance is None else generation_metrics.context_relevance,
                }
            )

        end_to_end_metrics = await _score_end_to_end(
            embedding_client=embedding_client,
            question=sample.question,
            answer=answer,
            gold_answer=sample.gold_answer,
            judge_model=options.judge_model or options.generation_model,
            use_llm_judge=options.use_llm_judge,
        )

        results.append(
            SampleEvaluationResult(
                sample_id=sample.sample_id,
                question=sample.question,
                retrieval=retrieval_metrics,
                generation=generation_metrics,
                end_to_end=end_to_end_metrics,
                answer=answer,
                contexts=contexts,
            )
        )

    summary = EvaluationSummary(
        dataset_name=dataset.dataset_name,
        dataset_version=dataset.version,
        sample_count=len(results),
        retrieval=average_retrieval_metrics([item.retrieval for item in results]),
        generation=average_generation_metrics([item.generation for item in results]),
        end_to_end=average_end_to_end_metrics([item.end_to_end for item in results]),
        metadata={
            "top_k": options.top_k,
            "use_ragas": options.use_ragas,
            "use_llm_judge": options.use_llm_judge,
        },
    )
    report = EvaluationReport(summary=summary, samples=results)
    _write_report(report, options.output_path)
    return report


async def _generate_answer(*, question: str, gold_answer: str, contexts: list[RetrievedChunk], generation_model: str) -> str:
    from services.llm_service import create_text_response
    from services.rag_service import build_rag_prompt

    prompt = build_rag_prompt(question, [item.model_dump() for item in contexts], "")
    content = await create_text_response(
        model=generation_model,
        input_messages=[{"role": "user", "content": prompt}],
        max_output_tokens=1000,
    )
    return content.strip() or ""


async def _score_end_to_end(*, embedding_client, question: str, answer: str, gold_answer: str, judge_model: str, use_llm_judge: bool) -> EndToEndMetrics:
    from config import settings

    semantic_similarity = None
    try:
        response = await embedding_client.embeddings.create(input=[answer, gold_answer], model=settings.embedding_model)
        vectors = [item.embedding for item in response.data]
        if len(vectors) == 2:
            semantic_similarity = cosine_similarity(vectors[0], vectors[1])
    except Exception:
        semantic_similarity = None

    metrics = EndToEndMetrics(semantic_similarity=semantic_similarity)
    if not use_llm_judge:
        return metrics
    judged = await judge_correctness(model=judge_model, question=question, answer=answer, gold_answer=gold_answer)
    return metrics.model_copy(
        update={
            "correctness_score": judged.correctness_score,
            "correctness_label": judged.correctness_label,
            "correctness_reason": judged.correctness_reason,
        }
    )


def _to_retrieved_chunk(item: dict) -> RetrievedChunk:
    return RetrievedChunk(
        filename=str(item.get("filename") or "未命名文档"),
        content=str(item.get("content") or ""),
        source_type=str(item.get("source_type") or "unknown"),
        metadata=item.get("metadata") or {},
        score=item.get("score"),
    )


def _write_report(report: EvaluationReport, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def run_from_cli(options: EvaluationOptions) -> EvaluationReport:
    return asyncio.run(run_evaluation(options))
