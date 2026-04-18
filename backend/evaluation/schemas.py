from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


QuestionType = Literal["fact", "explanation", "process", "locate", "other"]


class GoldChunkMatcher(BaseModel):
    filename: Optional[str] = Field(default=None, description="Expected source filename.")
    content_substring: Optional[str] = Field(default=None, description="Snippet that should appear in the chunk.")
    chunk_index: Optional[int] = Field(default=None, description="Optional exact chunk index if known.")


class EvaluationSample(BaseModel):
    sample_id: str = Field(description="Stable identifier for the sample.")
    question: str
    question_type: QuestionType = "other"
    gold_answer: str
    gold_chunks: list[GoldChunkMatcher] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class EvaluationDataset(BaseModel):
    dataset_name: str
    version: str = "v1"
    samples: list[EvaluationSample]


class RetrievedChunk(BaseModel):
    filename: str = "未命名文档"
    content: str
    source_type: str = "unknown"
    metadata: dict = Field(default_factory=dict)
    score: Optional[float] = None


class RetrievalMetrics(BaseModel):
    recall_at_5: float
    precision_at_5: float
    hit_rate_at_5: float
    mrr: float
    matched_chunks: int
    relevant_chunks: int
    retrieved_chunks: int


class GenerationMetrics(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevance: Optional[float] = None
    context_relevance: Optional[float] = None
    judge_score: Optional[float] = None
    judge_label: Optional[str] = None
    judge_reason: Optional[str] = None


class EndToEndMetrics(BaseModel):
    semantic_similarity: Optional[float] = None
    correctness_score: Optional[float] = None
    correctness_label: Optional[str] = None
    correctness_reason: Optional[str] = None


class SampleEvaluationResult(BaseModel):
    sample_id: str
    question: str
    retrieval: RetrievalMetrics
    generation: GenerationMetrics
    end_to_end: EndToEndMetrics
    answer: str
    contexts: list[RetrievedChunk] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    dataset_name: str
    dataset_version: str
    sample_count: int
    retrieval: RetrievalMetrics
    generation: GenerationMetrics
    end_to_end: EndToEndMetrics
    metadata: dict = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    summary: EvaluationSummary
    samples: list[SampleEvaluationResult]
