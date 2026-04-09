"""Prompt exports grouped by business capability."""

# GitHub PR 自动审查
from .github_pr_review import REVIEW_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT, TEST_SYSTEM_PROMPT_COMPACT
from .github_pr_testing import TEST_COVERAGE_ANALYSIS_PROMPT, UNIT_TEST_GENERATION_PROMPT, UNIT_TEST_GENERATION_PROMPT_COMPACT

# 手动 Code Review
from .manual_code_review import CODE_REVIEW_SYSTEM_PROMPT

# RAG 知识库问答
from .rag_answer import RAG_PROMPT_TEMPLATE
from .rag_query_rewrite import QUERY_REWRITE_PROMPT

# 对话记忆
from .chat_memory import EXTRACT_MEMORY_PROMPT, SUMMARY_PROMPT

__all__ = [
    # 手动 Code Review
    "CODE_REVIEW_SYSTEM_PROMPT",

    # 对话记忆
    "EXTRACT_MEMORY_PROMPT",
    "SUMMARY_PROMPT",

    # RAG 知识库问答
    "QUERY_REWRITE_PROMPT",
    "RAG_PROMPT_TEMPLATE",

    # GitHub PR 自动审查
    "REVIEW_SYSTEM_PROMPT",
    "TEST_COVERAGE_ANALYSIS_PROMPT",
    "TEST_SYSTEM_PROMPT",
    "TEST_SYSTEM_PROMPT_COMPACT",
    "UNIT_TEST_GENERATION_PROMPT",
    "UNIT_TEST_GENERATION_PROMPT_COMPACT",
]
