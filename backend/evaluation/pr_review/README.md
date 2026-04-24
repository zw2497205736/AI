# PR Review Offline Evaluation

这套模块用于评估当前 GitHub PR Agent 在 `Code Review`、`测试建议`、`单元测试建议` 三类输出上的质量。

它的目标不是替代线上流程，而是给后续这些改动提供一个稳定的离线验证基线：

- 调 Prompt
- 调 Planner / Executor / Replanner
- 调上下文拼装逻辑
- 调知识检索注入策略
- 调工具系统

一句话说：

> 它要解决的是“改完 Agent 之后，怎么证明真的变好了”。

---

## 1. 评测目标

第一阶段先聚焦 4 个问题：

1. 关键风险有没有识别出来
2. 输出是不是太空泛
3. 测试建议能不能落地
4. 同类 PR 输出是否稳定

当前不追求：

- 100% 自动打分
- 完全替代人工判断
- 一次性覆盖所有语言和场景

第一版更适合走：

- **结构化数据集**
- **规则指标**
- **可选 LLM Judge**
- **人工 spot check**

---

## 2. 评测对象

建议按当前 PR Agent 三个阶段拆开评：

### 2.1 Review 阶段

关注：

- 是否识别功能逻辑问题
- 是否识别边界条件问题
- 是否识别回归风险
- 是否有具体证据

### 2.2 Test Suggestion 阶段

关注：

- 是否覆盖主路径
- 是否覆盖边界输入
- 是否覆盖异常路径
- 是否能给出可执行测试点

### 2.3 Unit Test 阶段

关注：

- 是否指出测试对象
- 是否给出输入/断言方向
- 是否识别需要 mock 的依赖
- 示例代码是否贴近目标语言/框架

---

## 3. 数据集设计

数据集建议每条样本描述一次完整 PR 审查场景，而不是只给最终答案。

最小字段建议如下：

| 字段 | 说明 |
| --- | --- |
| `sample_id` | 样本唯一 ID |
| `repo_name` | 仓库名或仓库标识 |
| `pr_number` | PR 编号，可选 |
| `title` | PR 标题 |
| `body` | PR 描述 |
| `changed_files` | 变更文件列表 |
| `diff_text` | 可评审的 diff 文本 |
| `ground_truth` | 结构化标准答案 |
| `metadata` | 语言、类型、来源等扩展信息 |

---

## 4. Ground Truth 建议结构

第一版不要直接标完整 markdown，而建议标“结构化标准答案”。

原因：

- 更稳定
- 更容易自动比对
- 更适合以后换 Prompt

推荐结构：

- `must_find_issues`
- `optional_issues`
- `test_focuses`
- `unit_test_targets`
- `merge_recommendation`

其中：

### `must_find_issues`

表示高风险问题，如果没识别出来，应视为明显漏报。

每条 issue 至少包含：

- `title`
- `severity`
- `file`
- `reason`
- `expected_keywords`

### `optional_issues`

表示识别到会加分，但没识别到不一定算失败。

### `test_focuses`

描述测试建议至少该覆盖哪些重点，比如：

- 空值输入
- 非法状态切换
- 幂等重复调用
- 下游依赖失败

### `unit_test_targets`

描述 unit test 建议应该靠近哪些对象，比如：

- 某个函数/方法
- 某个模块
- 某个状态变更逻辑

---

## 5. 第一版指标建议

第一版建议先做“少而稳”的指标。

### 5.1 Review 指标

| 指标 | 含义 |
| --- | --- |
| `must_find_recall` | 高风险问题命中率 |
| `precision_hint` | 输出中是否出现明显误报 |
| `specificity_score` | 是否指向具体文件、函数、行为 |
| `vagueness_score` | 评审输出是否空泛，越低越好 |
| `merge_judgement_match` | 合并建议是否与标准答案一致 |

### 5.2 Test Suggestion 指标

| 指标 | 含义 |
| --- | --- |
| `test_focus_coverage` | 是否覆盖关键测试重点 |
| `actionability_score` | 建议是否可直接转为测试任务 |
| `risk_regression_coverage` | 是否识别关键回归点 |
| `vagueness_score` | 测试建议是否停留在空泛表述 |

### 5.3 Unit Test 指标

| 指标 | 含义 |
| --- | --- |
| `target_alignment` | 是否指向正确测试对象 |
| `assertion_quality` | 是否提出了有效断言方向 |
| `mock_awareness` | 是否识别需要 mock 的依赖 |
| `skeleton_presence` | 是否给出了最小可用骨架 |
| `vagueness_score` | 单测建议是否过于抽象，越低越好 |

### 5.4 跨阶段指标

| 指标 | 含义 |
| --- | --- |
| `format_stability` | 输出结构是否稳定 |
| `empty_output_rate` | 空输出或失败输出比例 |
| `fallback_rate` | 运行过程中的 fallback 比例 |
| `replan_rate` | 重规划频率 |

---

## 6. 打分策略建议

建议分三层：

### 层 1：规则打分

适合先做、也最稳定：

- 关键词命中
- 是否提到指定文件
- 是否提到核心函数/对象
- 是否出现合并建议
- 是否存在示例代码块

### 层 2：结构打分

检查输出是否满足预期结构，例如：

- 是否有 `评审概览`
- 是否有 `高风险问题`
- 是否有 `最终建议`
- 是否有 `测试重点`
- 是否有 `示例测试代码`

### 层 3：LLM Judge

只作为可选增强，不建议一开始完全依赖。

建议让 LLM Judge 判断：

- 是否抓到了真实工程风险
- 是否存在明显空话
- 测试建议是否可执行
- 单测建议是否贴当前改动

当前 PR Review 评测也已支持可选 Judge 分，分别对：

- `review`
- `test_suggestion`
- `unit_test`

三个阶段独立给出 `judge_score / judge_label / judge_reason`。

## 6.1 样本级诊断

当前报告除了分数，还会补样本级诊断字段，便于后续调 Prompt：

- review 命中了哪些 must-find issue
- review 漏了哪些 must-find issue
- review 出现了哪些泛化短语
- test 建议漏了哪些 test focus
- unit test 建议漏了哪些 target
- 哪些阶段为空、失败、缺少标题结构

---

## 7. 样本分类建议

为了避免评测集只覆盖一种场景，建议至少按这些维度分类：

| 维度 | 建议分类 |
| --- | --- |
| 语言 | Python / TypeScript / Java / Go |
| PR 类型 | bugfix / refactor / backend_api_change / frontend_ui_change / test_only / config_change |
| 风险等级 | high / medium / low |
| 文件规模 | small / medium / large |
| 是否依赖知识库 | yes / no |

第一版不需要全量覆盖，但建议至少：

- bugfix
- backend_api_change
- test_only

这三类先覆盖。

---

## 8. 最小执行流程

第一版 runner 可以按下面流程做：

1. 读取 PR review 数据集
2. 根据样本构造 `PRReviewAgentState` 所需最小输入
3. 分别执行：
   - review 生成
   - test_suggestion 生成
   - unit_test 生成
4. 对照 ground truth 打分
5. 输出 summary report + per-sample report

这里第一版甚至可以先不跑完整 Planner / Executor 循环，而是先支持两种模式：

- `stage_only`
- `full_agent`

这样便于区分问题到底出在：

- prompt 本身
- 还是编排逻辑

当前仓库已落第一版最小 skeleton：

- `backend/evaluation/pr_review/schemas.py`
- `backend/evaluation/pr_review/dataset_loader.py`
- `backend/evaluation/pr_review/metrics.py`
- `backend/evaluation/pr_review/runner.py`
- `backend/evaluation/pr_review/cli.py`
- `backend/evaluation/pr_review/compare_cli.py`

当前只支持：

- `stage_only`
- `full_agent`

其中：

- `stage_only`：直接复用阶段生成逻辑，适合先测 Prompt 本身
- `full_agent`：离线模拟 planner / executor / replanner 主循环，但工具读取样本本地数据，不访问 GitHub

当前示例数据集也已经补成一个小型开发集，覆盖：

- `bugfix`
- `backend_api_change`
- `test_only`
- `frontend_ui_change`
- `config_change`

---

## 9. 推荐的首批实现顺序

### Step 1

先定义：

- 数据集 schema
- 示例数据
- 报告结构

### Step 2

先做纯规则指标：

- must_find recall
- specificity
- actionability
- skeleton presence

### Step 3

再加可选 LLM Judge。

### Step 4

最后再接入：

- full_agent 模式
- 多版本对比

---

## 10. 当前阶段建议的成功标准

如果满足下面几点，就说明第一版评测框架已经有价值：

1. 能跑最小样本集
2. 能输出稳定 JSON 报告
3. 能比较两个 Prompt 版本
4. 能识别“具体性变差”或“漏报变多”
5. 团队能拿它讨论 Agent 质量，而不是只能靠感觉

## 11. 当前运行方式

在 `backend` 目录执行：

```bash
python -m evaluation.pr_review.cli \
  --dataset evaluation/pr_review/pr_review_eval_dataset.example.json
```

运行离线 `full_agent` 模式：

```bash
python -m evaluation.pr_review.cli \
  --dataset evaluation/pr_review/pr_review_eval_dataset.example.json \
  --mode full_agent
```

导出 Markdown 报告：

```bash
python -m evaluation.pr_review.cli \
  --dataset evaluation/pr_review/pr_review_eval_dataset.example.json \
  --markdown-output evaluation/output/pr_review_report.md
```

开启 LLM Judge：

```bash
python -m evaluation.pr_review.cli \
  --dataset evaluation/pr_review/pr_review_eval_dataset.example.json \
  --use-llm-judge \
  --judge-model glm-4.5-air
```

运行 A/B 对比：

```bash
python -m evaluation.pr_review.compare_cli \
  --dataset evaluation/pr_review/pr_review_eval_dataset.example.json \
  --baseline-label stage_only \
  --candidate-label full_agent \
  --baseline-mode stage_only \
  --candidate-mode full_agent \
  --markdown-output evaluation/output/pr_review_compare.md
```

---

## 12. 后续扩展方向

后面可以逐步扩展：

- 增加人工标注工作流
- 增加样本版本对比
- 增加 PR 类型切片统计
- 增加 trace 与质量指标关联分析
- 增加 repo-level memory 的评测维度
