from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


Severity = Literal["high", "medium", "low"]
MergeRecommendation = Literal["approve", "approve_with_notes", "changes_requested", "uncertain"]
ExecutionMode = Literal["stage_only", "full_agent"]


class ChangedFile(BaseModel):
    filename: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0


class GroundTruthIssue(BaseModel):
    title: str
    severity: Severity
    file: Optional[str] = None
    reason: str
    expected_keywords: list[str] = Field(default_factory=list)


class OptionalIssue(BaseModel):
    title: str
    severity: Optional[Severity] = None


class GroundTruth(BaseModel):
    must_find_issues: list[GroundTruthIssue] = Field(default_factory=list)
    optional_issues: list[OptionalIssue] = Field(default_factory=list)
    test_focuses: list[str] = Field(default_factory=list)
    unit_test_targets: list[str] = Field(default_factory=list)
    merge_recommendation: MergeRecommendation


class PRReviewEvaluationSample(BaseModel):
    sample_id: str
    repo_name: str = "unknown/repo"
    pr_number: Optional[int] = None
    title: str
    body: str = ""
    changed_files: list[ChangedFile] = Field(default_factory=list)
    diff_text: str
    ground_truth: GroundTruth
    metadata: dict = Field(default_factory=dict)


class PRReviewEvaluationDataset(BaseModel):
    dataset_name: str
    version: str = "v1"
    samples: list[PRReviewEvaluationSample]


class ReviewStageMetrics(BaseModel):
    must_find_recall: float = 0.0
    precision_hint: float = 0.0
    specificity_score: float = 0.0
    vagueness_score: float = 0.0
    merge_judgement_match: float = 0.0


class TestSuggestionMetrics(BaseModel):
    test_focus_coverage: float = 0.0
    actionability_score: float = 0.0
    risk_regression_coverage: float = 0.0
    vagueness_score: float = 0.0


class UnitTestMetrics(BaseModel):
    target_alignment: float = 0.0
    mock_awareness: float = 0.0
    skeleton_presence: float = 0.0
    assertion_quality: float = 0.0
    vagueness_score: float = 0.0


class CrossStageMetrics(BaseModel):
    format_stability: float = 0.0
    empty_output: float = 0.0
    failed_output: float = 0.0


class StageJudgeMetrics(BaseModel):
    judge_score: Optional[float] = None
    judge_label: Optional[str] = None
    judge_reason: Optional[str] = None


class PRReviewStageOutputs(BaseModel):
    review_content: str = ""
    test_suggestion_content: str = ""
    unit_test_generation_content: str = ""


class ReviewDiagnostics(BaseModel):
    matched_issue_titles: list[str] = Field(default_factory=list)
    missed_issue_titles: list[str] = Field(default_factory=list)
    matched_issue_keywords: list[str] = Field(default_factory=list)
    unsupported_risk_terms: list[str] = Field(default_factory=list)
    generic_phrases: list[str] = Field(default_factory=list)
    merge_recommendation_matched: bool = False


class TestDiagnostics(BaseModel):
    covered_focuses: list[str] = Field(default_factory=list)
    missed_focuses: list[str] = Field(default_factory=list)
    generic_phrases: list[str] = Field(default_factory=list)
    actionable_markers: list[str] = Field(default_factory=list)


class UnitTestDiagnostics(BaseModel):
    matched_targets: list[str] = Field(default_factory=list)
    missed_targets: list[str] = Field(default_factory=list)
    generic_phrases: list[str] = Field(default_factory=list)
    evidence_markers: list[str] = Field(default_factory=list)


class CrossStageDiagnostics(BaseModel):
    empty_stages: list[str] = Field(default_factory=list)
    failed_stages: list[str] = Field(default_factory=list)
    missing_headings: list[str] = Field(default_factory=list)


class PRReviewSampleEvaluationResult(BaseModel):
    sample_id: str
    outputs: PRReviewStageOutputs
    review_metrics: ReviewStageMetrics
    review_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    review_diagnostics: ReviewDiagnostics
    test_metrics: TestSuggestionMetrics
    test_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    test_diagnostics: TestDiagnostics
    unit_test_metrics: UnitTestMetrics
    unit_test_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    unit_test_diagnostics: UnitTestDiagnostics
    cross_stage_metrics: CrossStageMetrics
    cross_stage_diagnostics: CrossStageDiagnostics
    metadata: dict = Field(default_factory=dict)


class PRReviewEvaluationSummary(BaseModel):
    dataset_name: str
    dataset_version: str
    sample_count: int
    execution_mode: ExecutionMode
    review_metrics: ReviewStageMetrics
    review_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    test_metrics: TestSuggestionMetrics
    test_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    unit_test_metrics: UnitTestMetrics
    unit_test_judge: StageJudgeMetrics = Field(default_factory=StageJudgeMetrics)
    cross_stage_metrics: CrossStageMetrics
    metadata: dict = Field(default_factory=dict)


class PRReviewEvaluationReport(BaseModel):
    summary: PRReviewEvaluationSummary
    samples: list[PRReviewSampleEvaluationResult]


class PRReviewComparisonSampleDelta(BaseModel):
    sample_id: str
    review_recall_delta: float = 0.0
    review_precision_delta: float = 0.0
    review_vagueness_delta: float = 0.0
    test_coverage_delta: float = 0.0
    test_vagueness_delta: float = 0.0
    unit_alignment_delta: float = 0.0
    unit_vagueness_delta: float = 0.0
    review_judge_delta: Optional[float] = None
    test_judge_delta: Optional[float] = None
    unit_judge_delta: Optional[float] = None
    regression_flags: list[str] = Field(default_factory=list)


class PRReviewComparisonReport(BaseModel):
    baseline_label: str
    candidate_label: str
    baseline_summary: PRReviewEvaluationSummary
    candidate_summary: PRReviewEvaluationSummary
    metric_deltas: dict[str, Optional[float]] = Field(default_factory=dict)
    sample_deltas: list[PRReviewComparisonSampleDelta] = Field(default_factory=list)
