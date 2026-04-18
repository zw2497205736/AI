from __future__ import annotations

import math
from typing import Iterable, Optional

from .schemas import EndToEndMetrics, GenerationMetrics, GoldChunkMatcher, RetrievedChunk, RetrievalMetrics


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def chunk_matches_gold(chunk: RetrievedChunk, matcher: GoldChunkMatcher) -> bool:
    if matcher.filename and matcher.filename != chunk.filename:
        return False
    if matcher.chunk_index is not None:
        actual_index = chunk.metadata.get("chunk_index")
        if actual_index != matcher.chunk_index:
            return False
    if matcher.content_substring:
        if _normalize_text(matcher.content_substring) not in _normalize_text(chunk.content):
            return False
    return True


def compute_retrieval_metrics(chunks: list[RetrievedChunk], gold_chunks: list[GoldChunkMatcher], top_k: int = 5) -> RetrievalMetrics:
    top_chunks = chunks[:top_k]
    if not gold_chunks:
        return RetrievalMetrics(
            recall_at_5=0.0,
            precision_at_5=0.0,
            hit_rate_at_5=0.0,
            mrr=0.0,
            matched_chunks=0,
            relevant_chunks=0,
            retrieved_chunks=len(top_chunks),
        )

    matched_gold_indexes: set[int] = set()
    matched_retrieved_indexes: set[int] = set()
    reciprocal_rank = 0.0

    for retrieved_index, chunk in enumerate(top_chunks, start=1):
        for gold_index, matcher in enumerate(gold_chunks):
            if chunk_matches_gold(chunk, matcher):
                matched_gold_indexes.add(gold_index)
                matched_retrieved_indexes.add(retrieved_index - 1)
                if reciprocal_rank == 0.0:
                    reciprocal_rank = 1.0 / retrieved_index

    recall = len(matched_gold_indexes) / len(gold_chunks) if gold_chunks else 0.0
    precision = len(matched_retrieved_indexes) / len(top_chunks) if top_chunks else 0.0
    hit_rate = 1.0 if matched_retrieved_indexes else 0.0

    return RetrievalMetrics(
        recall_at_5=recall,
        precision_at_5=precision,
        hit_rate_at_5=hit_rate,
        mrr=reciprocal_rank,
        matched_chunks=len(matched_gold_indexes),
        relevant_chunks=len(gold_chunks),
        retrieved_chunks=len(top_chunks),
    )


def cosine_similarity(v1: Iterable[float], v2: Iterable[float]) -> float:
    vec1 = list(v1)
    vec2 = list(v2)
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def average_retrieval_metrics(items: list[RetrievalMetrics]) -> RetrievalMetrics:
    if not items:
        return RetrievalMetrics(
            recall_at_5=0.0,
            precision_at_5=0.0,
            hit_rate_at_5=0.0,
            mrr=0.0,
            matched_chunks=0,
            relevant_chunks=0,
            retrieved_chunks=0,
        )
    return RetrievalMetrics(
        recall_at_5=sum(item.recall_at_5 for item in items) / len(items),
        precision_at_5=sum(item.precision_at_5 for item in items) / len(items),
        hit_rate_at_5=sum(item.hit_rate_at_5 for item in items) / len(items),
        mrr=sum(item.mrr for item in items) / len(items),
        matched_chunks=sum(item.matched_chunks for item in items),
        relevant_chunks=sum(item.relevant_chunks for item in items),
        retrieved_chunks=sum(item.retrieved_chunks for item in items),
    )


def average_generation_metrics(items: list[GenerationMetrics]) -> GenerationMetrics:
    return GenerationMetrics(
        faithfulness=_average_optional([item.faithfulness for item in items]),
        answer_relevance=_average_optional([item.answer_relevance for item in items]),
        context_relevance=_average_optional([item.context_relevance for item in items]),
        judge_score=_average_optional([item.judge_score for item in items]),
    )


def average_end_to_end_metrics(items: list[EndToEndMetrics]) -> EndToEndMetrics:
    return EndToEndMetrics(
        semantic_similarity=_average_optional([item.semantic_similarity for item in items]),
        correctness_score=_average_optional([item.correctness_score for item in items]),
    )


def _average_optional(values: list[Optional[float]]) -> Optional[float]:
    actual = [value for value in values if value is not None]
    if not actual:
        return None
    return sum(actual) / len(actual)
