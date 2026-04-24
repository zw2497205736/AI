from __future__ import annotations

import re
from typing import Iterable

from .schemas import (
    CrossStageMetrics,
    CrossStageDiagnostics,
    GroundTruthIssue,
    PRReviewStageOutputs,
    ReviewDiagnostics,
    ReviewStageMetrics,
    TestDiagnostics,
    TestSuggestionMetrics,
    UnitTestDiagnostics,
    UnitTestMetrics,
)


def evaluate_review_output(review_output: str, issues: list[GroundTruthIssue], merge_recommendation: str) -> ReviewStageMetrics:
    diagnostics = diagnose_review_output(review_output, issues, merge_recommendation)

    must_find_recall = len(diagnostics.matched_issue_titles) / len(issues) if issues else 1.0
    specificity_raw = 0.0
    if issues:
        file_hits = sum(1 for issue in issues if issue.file and _normalize(issue.file) in _normalize(review_output))
        specificity_raw += file_hits / len(issues)
    specificity_raw += 1.0 if re.search(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]+\(", review_output) else 0.0
    specificity_score = min(1.0, specificity_raw / 2)
    precision_hint = _review_precision_hint(review_output, issues)
    vagueness_score = _vagueness_score(review_output, stage="review")

    merge_match = 1.0 if diagnostics.merge_recommendation_matched else 0.0
    return ReviewStageMetrics(
        must_find_recall=must_find_recall,
        precision_hint=precision_hint,
        specificity_score=specificity_score,
        vagueness_score=vagueness_score,
        merge_judgement_match=merge_match,
    )


def evaluate_test_output(test_output: str, test_focuses: list[str]) -> TestSuggestionMetrics:
    diagnostics = diagnose_test_output(test_output, test_focuses)
    matched_focuses = len(diagnostics.covered_focuses)
    actionability_score = 1.0 if diagnostics.actionable_markers else 0.0
    normalized = _normalize(test_output)
    regression_coverage = 1.0 if any(keyword in normalized for keyword in ["回归", "异常", "边界", "并发", "空值"]) else 0.0
    return TestSuggestionMetrics(
        test_focus_coverage=(matched_focuses / len(test_focuses) if test_focuses else 1.0),
        actionability_score=actionability_score,
        risk_regression_coverage=regression_coverage,
        vagueness_score=_vagueness_score(test_output, stage="test"),
    )


def evaluate_unit_test_output(unit_output: str, unit_test_targets: list[str]) -> UnitTestMetrics:
    diagnostics = diagnose_unit_test_output(unit_output, unit_test_targets)
    normalized = _normalize(unit_output)
    matched_targets = len(diagnostics.matched_targets)
    mock_awareness = 1.0 if any(keyword in normalized for keyword in ["mock", "stub", "patch", "依赖", "模拟"]) else 0.0
    skeleton_presence = 1.0 if "```" in unit_output or re.search(r"\bdef test_|\bit\(|\btest\(", unit_output) else 0.0
    assertion_quality = 1.0 if any(keyword in normalized for keyword in ["断言", "assert", "expected", "返回值"]) else 0.0
    return UnitTestMetrics(
        target_alignment=(matched_targets / len(unit_test_targets) if unit_test_targets else 1.0),
        mock_awareness=mock_awareness,
        skeleton_presence=skeleton_presence,
        assertion_quality=assertion_quality,
        vagueness_score=_vagueness_score(unit_output, stage="unit_test"),
    )


def evaluate_cross_stage(outputs: PRReviewStageOutputs) -> CrossStageMetrics:
    diagnostics = diagnose_cross_stage(outputs)
    empty_count = len(diagnostics.empty_stages)
    failed_count = len(diagnostics.failed_stages)
    format_stability = (3 - len(diagnostics.missing_headings)) / 3
    return CrossStageMetrics(
        format_stability=format_stability,
        empty_output=empty_count / 3,
        failed_output=failed_count / 3,
    )


def diagnose_review_output(review_output: str, issues: list[GroundTruthIssue], merge_recommendation: str) -> ReviewDiagnostics:
    normalized = _normalize(review_output)
    matched_issue_titles: list[str] = []
    missed_issue_titles: list[str] = []
    matched_issue_keywords: list[str] = []
    for issue in issues:
        keywords = [_normalize(item) for item in issue.expected_keywords if item.strip()]
        issue_matched = False
        for keyword in keywords:
            if keyword in normalized:
                issue_matched = True
                matched_issue_keywords.append(keyword)
        if issue_matched:
            matched_issue_titles.append(issue.title)
        else:
            missed_issue_titles.append(issue.title)

    unsupported_terms = [item for item in _unsupported_risk_terms() if item in normalized and item not in matched_issue_keywords]
    generic_phrases = [item for item in _generic_warning_phrases() if item in normalized]
    return ReviewDiagnostics(
        matched_issue_titles=matched_issue_titles,
        missed_issue_titles=missed_issue_titles,
        matched_issue_keywords=sorted(set(matched_issue_keywords)),
        unsupported_risk_terms=unsupported_terms,
        generic_phrases=generic_phrases,
        merge_recommendation_matched=_merge_recommendation_matches(review_output, merge_recommendation),
    )


def diagnose_test_output(test_output: str, test_focuses: list[str]) -> TestDiagnostics:
    normalized = _normalize(test_output)
    covered = [item for item in test_focuses if _normalize(item) in normalized]
    missed = [item for item in test_focuses if _normalize(item) not in normalized]
    generic_phrases = [item for item in _generic_warning_phrases() if item in normalized] + [
        item for item in _stage_generic_phrases("test") if item in normalized
    ]
    actionable_markers = [item for item in ["输入", "预期", "断言", "场景", "用例"] if item in normalized]
    return TestDiagnostics(
        covered_focuses=covered,
        missed_focuses=missed,
        generic_phrases=sorted(set(generic_phrases)),
        actionable_markers=actionable_markers,
    )


def diagnose_unit_test_output(unit_output: str, unit_test_targets: list[str]) -> UnitTestDiagnostics:
    normalized = _normalize(unit_output)
    matched = [item for item in unit_test_targets if _normalize(item) in normalized]
    missed = [item for item in unit_test_targets if _normalize(item) not in normalized]
    generic_phrases = [item for item in _generic_warning_phrases() if item in normalized] + [
        item for item in _stage_generic_phrases("unit_test") if item in normalized
    ]
    evidence_markers = []
    for marker in ["mock", "assert", "断言", "返回值", "输入", "```"]:
        if marker in normalized or marker in unit_output:
            evidence_markers.append(marker)
    return UnitTestDiagnostics(
        matched_targets=matched,
        missed_targets=missed,
        generic_phrases=sorted(set(generic_phrases)),
        evidence_markers=sorted(set(evidence_markers)),
    )


def diagnose_cross_stage(outputs: PRReviewStageOutputs) -> CrossStageDiagnostics:
    stage_map = {
        "review": outputs.review_content or "",
        "test_suggestion": outputs.test_suggestion_content or "",
        "unit_test": outputs.unit_test_generation_content or "",
    }
    empty_stages = [stage for stage, content in stage_map.items() if not content.strip()]
    failed_stages = [stage for stage, content in stage_map.items() if content.startswith("生成失败：")]
    missing_headings = [stage for stage, content in stage_map.items() if "###" not in content]
    return CrossStageDiagnostics(
        empty_stages=empty_stages,
        failed_stages=failed_stages,
        missing_headings=missing_headings,
    )


def average_review_metrics(items: Iterable[ReviewStageMetrics]) -> ReviewStageMetrics:
    values = list(items)
    if not values:
        return ReviewStageMetrics()
    return ReviewStageMetrics(
        must_find_recall=sum(item.must_find_recall for item in values) / len(values),
        precision_hint=sum(item.precision_hint for item in values) / len(values),
        specificity_score=sum(item.specificity_score for item in values) / len(values),
        vagueness_score=sum(item.vagueness_score for item in values) / len(values),
        merge_judgement_match=sum(item.merge_judgement_match for item in values) / len(values),
    )


def average_test_metrics(items: Iterable[TestSuggestionMetrics]) -> TestSuggestionMetrics:
    values = list(items)
    if not values:
        return TestSuggestionMetrics()
    return TestSuggestionMetrics(
        test_focus_coverage=sum(item.test_focus_coverage for item in values) / len(values),
        actionability_score=sum(item.actionability_score for item in values) / len(values),
        risk_regression_coverage=sum(item.risk_regression_coverage for item in values) / len(values),
        vagueness_score=sum(item.vagueness_score for item in values) / len(values),
    )


def average_unit_test_metrics(items: Iterable[UnitTestMetrics]) -> UnitTestMetrics:
    values = list(items)
    if not values:
        return UnitTestMetrics()
    return UnitTestMetrics(
        target_alignment=sum(item.target_alignment for item in values) / len(values),
        mock_awareness=sum(item.mock_awareness for item in values) / len(values),
        skeleton_presence=sum(item.skeleton_presence for item in values) / len(values),
        assertion_quality=sum(item.assertion_quality for item in values) / len(values),
        vagueness_score=sum(item.vagueness_score for item in values) / len(values),
    )


def average_cross_stage_metrics(items: Iterable[CrossStageMetrics]) -> CrossStageMetrics:
    values = list(items)
    if not values:
        return CrossStageMetrics()
    return CrossStageMetrics(
        format_stability=sum(item.format_stability for item in values) / len(values),
        empty_output=sum(item.empty_output for item in values) / len(values),
        failed_output=sum(item.failed_output for item in values) / len(values),
    )


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _merge_recommendation_matches(text: str, merge_recommendation: str) -> bool:
    normalized = _normalize(text)
    mapping = {
        "approve": ["建议合并", "可以合并", "approve"],
        "approve_with_notes": ["可合并但", "建议合并但", "approve with notes"],
        "changes_requested": ["不建议合并", "建议修改后再合并", "changes requested"],
        "uncertain": ["需结合上下文确认", "暂无法判断", "uncertain"],
    }
    return any(keyword in normalized for keyword in mapping.get(merge_recommendation, []))


def _has_actionable_test_shape(text: str) -> bool:
    normalized = _normalize(text)
    return any(keyword in normalized for keyword in ["输入", "预期", "断言", "场景", "用例"])


def _review_precision_hint(text: str, issues: list[GroundTruthIssue]) -> float:
    normalized = _normalize(text)
    if not text.strip():
        return 0.0
    matched_keywords = set()
    for issue in issues:
        for keyword in issue.expected_keywords:
            item = _normalize(keyword)
            if item and item in normalized:
                matched_keywords.add(item)
    unsupported_risk_terms = sum(1 for item in _unsupported_risk_terms() if item in normalized and item not in matched_keywords)
    generic_penalty = sum(1 for item in _generic_warning_phrases() if item in normalized)
    evidence_bonus = 1 if re.search(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]+\(|/[\w\-.]+|[A-Za-z0-9_]+\.[A-Za-z0-9_]+", text) else 0
    raw = 1.0 + 0.15 * evidence_bonus - 0.12 * unsupported_risk_terms - 0.08 * generic_penalty
    return max(0.0, min(1.0, raw))


def _vagueness_score(text: str, *, stage: str) -> float:
    normalized = _normalize(text)
    if not normalized:
        return 1.0

    generic_hits = sum(1 for item in _generic_warning_phrases() if item in normalized)
    stage_generic_hits = sum(1 for item in _stage_generic_phrases(stage) if item in normalized)
    evidence_hits = 0
    if re.search(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]+\(|/[\w\-.]+|[A-Za-z0-9_]+\.[A-Za-z0-9_]+", text):
        evidence_hits += 1
    if any(keyword in normalized for keyword in ["输入", "输出", "断言", "异常", "边界", "mock", "返回值", "响应头"]):
        evidence_hits += 1
    heading_hits = text.count("###")
    raw = 0.15 + 0.18 * generic_hits + 0.15 * stage_generic_hits - 0.18 * evidence_hits - 0.05 * min(heading_hits, 4)
    return max(0.0, min(1.0, raw))


def _generic_warning_phrases() -> list[str]:
    return [
        "建议优化",
        "建议完善",
        "建议补充更多测试",
        "增强鲁棒性",
        "提高可维护性",
        "需要进一步优化",
        "可能存在一定风险",
        "建议关注",
    ]


def _stage_generic_phrases(stage: str) -> list[str]:
    mapping = {
        "review": ["代码结构", "可读性", "代码质量"],
        "test": ["补充测试", "边界测试", "增加测试覆盖"],
        "unit_test": ["补充单测", "增加断言", "完善 mock"],
    }
    return mapping.get(stage, [])


def _unsupported_risk_terms() -> list[str]:
    return [
        "安全",
        "sql 注入",
        "xss",
        "死锁",
        "内存泄漏",
        "权限绕过",
        "数据丢失",
        "竞态",
        "事务",
        "一致性",
    ]
