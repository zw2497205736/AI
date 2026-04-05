# Prompt 目录说明

该目录集中管理项目中的提示词模板，便于统一维护、迭代和面试讲解。

## 已有提示词

- `code_review.py`
  手动代码审查页面使用的 Prompt

- `agent.py`
  GitHub Agent 自动 PR 审查与测试建议 Prompt

- `rag.py`
  RAG 主回答 Prompt

- `memory.py`
  会话摘要与长期记忆提取 Prompt

- `query.py`
  查询改写 Prompt

- `testing.py`
  单元测试生成 Prompt
  单元测试覆盖率分析 Prompt

## 设计原则

每类 Prompt 建议尽量包含：

1. `Role`
   明确模型所扮演的角色

2. `Task`
   明确这次要完成的任务

3. `Constraints`
   明确禁止事项、优先级和边界

4. `Format`
   明确输出结构，方便前端展示和后续处理

## 使用建议

如果后续要在项目中落地：

- `UNIT_TEST_GENERATION_PROMPT`
  可用于“根据 diff 生成单元测试建议或样例测试代码”

- `TEST_COVERAGE_ANALYSIS_PROMPT`
  可用于“根据 diff + 现有测试分析覆盖不足点”

建议：
- 生成单元测试与覆盖率分析尽量不要完全由同一个模型、同一轮结果互相评判
- 如果要更严谨，可以使用不同模型或不同提示词版本交叉验证
