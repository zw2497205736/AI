# GitHub PR Agent Harness Roadmap

## 1. 文档目标

这份文档不是再解释概念，而是把 `harness engineering.md` 里的分析，转成一份更适合执行的路线图。

目标有三个：

1. 明确这个 PR Agent 下一阶段应该先做什么
2. 把“能力建设”转成“可落地任务”
3. 给后续排期、拆人、验收提供一个统一参考

这份路线图默认面向当前仓库里的 GitHub PR Agent 主链路，核心代码入口主要包括：

- `backend/services/pr_review_agent_service.py`
- `backend/services/pr_review_tool_service.py`
- `backend/services/agent_service.py`
- `backend/prompts/pr_review_agent_planner.py`
- `backend/prompts/pr_review_agent_executor.py`
- `backend/prompts/pr_review_agent_replanner.py`
- `backend/routers/github_router.py`
- `frontend/src/pages/GithubAgentPage.tsx`

---

## 2. 总体判断

当前系统已经具备这些基础：

- 有 Planner / Executor / Replanner / Reporter
- 有工具系统
- 有任务状态与 trace
- 有前端执行轨迹展示
- 有规则兜底和失败补阶段

当前系统最缺的，不是“还能不能多写几个 Prompt”，而是三类基础设施：

1. **评估闭环**
2. **经验记忆**
3. **恢复工程**

所以整体路线建议是：

> 先补质量判断能力，再补经验复用能力，最后补生产级恢复能力。

---

## 3. 路线图总览

| Phase | 主题 | 核心目标 | 预期结果 |
| --- | --- | --- | --- |
| Phase 1 | 评估与观测补强 | 让系统可量化优化 | 能比较不同 Prompt / Agent 版本优劣 |
| Phase 2 | 上下文与记忆补强 | 让系统更贴仓库、更稳 | 长 PR 输出更稳，重复问题更少 |
| Phase 3 | 恢复工程与工具扩展 | 让系统更适合长期运行 | 重试、恢复、幂等、扩展能力更完善 |

---

## 4. Phase 1：先补评估与观测闭环

### 为什么先做这一阶段

如果没有评估体系，后面无论你：

- 改 Prompt
- 改工具
- 改编排
- 改上下文

都很难回答一个关键问题：

> 改完以后到底是变好了，还是只是“感觉变好了”？

所以这阶段是后续所有优化的基础。

### Phase 1 目标

- 建立 PR Review Agent 专属评测集
- 建立基础质量指标
- 建立 trace 到质量问题的映射关系
- 支持后续版本对比

### 任务包

| 任务编号 | 任务 | 说明 | 优先级 | 推荐入口 |
| --- | --- | --- | --- | --- |
| P1-1 | 定义 PR review 样本格式 | 约定输入、标准答案、风险点标注方式 | 最高 | 可新增 `backend/evaluation/pr_review/` |
| P1-2 | 建最小样本集 | 先做 20~50 条高质量样本，不求大但求稳 | 最高 | 可新增 `backend/evaluation/pr_review/examples/` |
| P1-3 | 定义质量指标 | 例如具体性、误报率、漏报率、可执行性 | 最高 | `backend/evaluation/metrics.py` |
| P1-4 | 增加 PR review runner | 跑指定版本 Prompt / Agent 逻辑 | 最高 | `backend/evaluation/runner.py` |
| P1-5 | 产出评测报告格式 | 支持 summary + per case 结果 | 高 | `backend/evaluation/schemas.py` |
| P1-6 | trace 统计分析 | 统计 fallback、replan、tool usage | 高 | `backend/services/pr_review_agent_service.py` |
| P1-7 | 版本对比脚本 | 支持对比 Prompt A/B 或编排变更前后 | 中 | 可新增 `backend/evaluation/cli.py` 参数 |

### 建议的最小评测指标

| 指标 | 定义 | 价值 |
| --- | --- | --- |
| 风险命中率 | 是否识别出关键问题 | 看 review 是否抓到重点 |
| 误报率 | 是否编造问题或夸大问题 | 控制 review 噪音 |
| 漏报率 | 是否遗漏高风险问题 | 控制 review 盲区 |
| 具体性 | 是否指向具体文件/函数/行为 | 判断输出是否空泛 |
| 测试建议可执行性 | 测试建议能否直接转成测试任务 | 判断测试建议是否有用 |
| 输出稳定性 | 同类样本输出结构是否一致 | 判断治理是否有效 |

### 验收标准

- 能跑一个最小 PR Review 离线评测集
- 能输出基础 summary 报告
- 能比较至少两个 Prompt/版本
- 能回答“最近一次改动有没有让结果更好”

### 风险点

- 样本标注成本高
- 如果指标设计太抽象，会很难落地
- 一开始不要追求完美自动评分，可以先做半自动评分

---

## 5. Phase 2：补上下文治理和经验记忆

### 为什么排在第二阶段

这一阶段会明显提升结果质量，但它依赖 Phase 1 提供验证手段。  
否则你做完 token budget 或 repo memory，也无法客观证明收益。

### Phase 2 目标

- 让长 PR 的输出更稳
- 让上下文更聚焦风险
- 让系统逐步具备 repo-level 经验能力

### 任务包 A：上下文治理

| 任务编号 | 任务 | 说明 | 优先级 | 推荐入口 |
| --- | --- | --- | --- | --- |
| P2-A1 | 加入 token budget 机制 | 不同上下文片段分配预算 | 高 | `backend/services/pr_review_agent_service.py` |
| P2-A2 | 增加文件风险排序 | 鉴权、状态变更、大 patch 文件优先 | 高 | `backend/services/github_service.py:126` |
| P2-A3 | 增加 diff 摘要层 | 文件级 summary 先于全量 patch | 高 | `backend/services/pr_review_agent_service.py:188` |
| P2-A4 | 按阶段定制上下文模板 | review/test/unit 三阶段不同视图 | 中 | `backend/services/pr_review_agent_service.py:168` |
| P2-A5 | 增加上下文调试信息 | 记录每次实际注入了哪些上下文块 | 中 | `backend/services/pr_review_agent_service.py:608` |

### 任务包 B：经验记忆

| 任务编号 | 任务 | 说明 | 优先级 | 推荐入口 |
| --- | --- | --- | --- | --- |
| P2-B1 | 定义 repo-level memory 结构 | 存团队偏好、常见风险、常见漏报 | 高 | 可新增 `backend/models/` / `backend/schemas/` |
| P2-B2 | 汇总历史任务模式 | 从最近任务中提炼高频问题类型 | 高 | `backend/services/pr_review_tool_service.py:60` |
| P2-B3 | 将记忆注入 planner | 让计划阶段参考历史经验 | 高 | `backend/services/pr_review_agent_service.py:284` |
| P2-B4 | 将记忆注入 stage prompt | 让 review/test 阶段更贴当前仓库 | 中 | `backend/services/pr_review_agent_service.py:188` |
| P2-B5 | 建人工反馈回流入口 | 后续支持采纳/驳回/修正回流 | 中 | `backend/routers/github_router.py` |

### 建议先做的最小版 memory

第一版不要做太复杂，可以先只支持这几类：

- `repo_review_focus`
- `common_regression_patterns`
- `preferred_test_framework`
- `recent_false_positive_patterns`

### 验收标准

- 长 PR 输出质量明显更稳
- 相同仓库下的 review 更贴团队风格
- planner 或 stage prompt 已能消费 repo-level memory
- evaluation 结果能证明至少一个指标改善

### 风险点

- 记忆如果无筛选，容易引入噪音
- repo memory 如果设计太重，会拖慢系统
- 需要避免“把历史偏见固化成永久规则”

---

## 6. Phase 3：补恢复工程与工具扩展

### 为什么放第三阶段

因为现在系统已经能跑，当前最大瓶颈不是完全跑不起来，而是：

- 结果不够可验证
- 输出不够可积累

等前两阶段完成后，再补恢复工程和工具扩展，收益会更大。

### Phase 3 目标

- 让系统更稳定
- 让失败恢复更精细
- 让工具系统更适合继续扩展

### 任务包 A：恢复工程

| 任务编号 | 任务 | 说明 | 优先级 | 推荐入口 |
| --- | --- | --- | --- | --- |
| P3-A1 | 建失败分类 | 区分 API / LLM / retrieval / persistence 失败 | 高 | `backend/services/pr_review_agent_service.py` |
| P3-A2 | 失败分类恢复策略 | 不同错误使用不同恢复方式 | 高 | `backend/services/pr_review_agent_service.py:332` |
| P3-A3 | 引入 degrade mode | 上下文不足或失败时走轻量模式 | 高 | `backend/prompts/pr_review_agent_executor.py` |
| P3-A4 | 做 checkpoint / resume | 从未完成阶段继续，而不是整单重跑 | 高 | `backend/services/agent_service.py` |
| P3-A5 | webhook 幂等去重 | 避免重复创建任务 | 高 | `backend/routers/github_router.py:180` |
| P3-A6 | 补充停止原因枚举 | finish 原因更明确 | 中 | `backend/services/pr_review_agent_service.py:498` |

### 任务包 B：工具扩展

| 任务编号 | 任务 | 说明 | 优先级 | 推荐入口 |
| --- | --- | --- | --- | --- |
| P3-B1 | 获取 PR review comments | 结合人工 review 信息 | 中 | `backend/services/pr_review_tool_service.py` |
| P3-B2 | 获取 PR commits | 看多次提交之间的修复演化 | 中 | `backend/services/pr_review_tool_service.py` |
| P3-B3 | 获取关联 issue 信息 | 让审查更理解业务背景 | 中 | `backend/services/pr_review_tool_service.py` |
| P3-B4 | 映射代码变更到测试目标 | 帮 unit test 建议更贴代码 | 中 | `backend/services/pr_review_tool_service.py` |
| P3-B5 | 工具结构化返回 | 为评估和前端复用做准备 | 中 | `backend/services/pr_review_tool_service.py` |

### 验收标准

- 常见失败不再只能 rerun 整单
- 相同 webhook 不会重复刷任务
- 至少一种降级模式可工作
- 工具扩展后不会让 executor 失控

### 风险点

- checkpoint 设计不清会让状态复杂度陡增
- 工具变多之后，路由复杂度也会增加
- 幂等和恢复要避免引入新的数据一致性问题

---

## 7. 建议的里程碑拆法

如果按比较现实的节奏推进，我建议拆成下面 4 个 milestone。

| Milestone | 范围 | 目标 |
| --- | --- | --- |
| M1 | Phase 1 最小版 | 先让 PR Agent 有最小评测能力 |
| M2 | Phase 2 上下文治理 | 长 PR 场景稳定性明显提升 |
| M3 | Phase 2 记忆接入 | repo-level memory 进入 planner/stage |
| M4 | Phase 3 恢复工程 | 幂等、checkpoint、失败分类可用 |

### M1 建议交付物

- PR review 样本 schema
- 20~50 条样本
- 最小 runner
- summary 报告

### M2 建议交付物

- token budget
- diff 风险排序
- 文件级摘要层
- context trace

### M3 建议交付物

- repo memory schema
- 历史任务摘要生成
- planner memory 注入
- stage prompt memory 注入

### M4 建议交付物

- 失败分类
- degrade mode
- webhook 幂等
- checkpoint / resume

---

## 8. 如果资源有限，最小可行版本怎么做

如果你现在人力有限，不建议一口气做全。

最小可行路线建议如下：

### MVP-1

- 建 20 条 PR Review 离线样本
- 做 3 个指标：
  - 风险命中率
  - 具体性
  - 测试建议可执行性

### MVP-2

- 给上下文加入预算控制
- 对文件做风险排序
- 记录实际注入上下文

### MVP-3

- 做 repo-level memory 最小版
- 先只注入 planner

### MVP-4

- 做 webhook 幂等
- 做一种 degrade mode

这样做的好处是：

- 每一步都能独立验证
- 每一步都能带来可见收益
- 不容易把系统一次性改得太重

---

## 9. 推荐的执行顺序

如果按真正动手的顺序，我建议：

1. 先做 `Phase 1 / P1-1 ~ P1-4`
2. 再做 `Phase 2 / P2-A1 ~ P2-A3`
3. 再做 `Phase 2 / P2-B1 ~ P2-B3`
4. 再做 `Phase 3 / P3-A1 ~ P3-A5`
5. 最后逐步扩展工具

原因很简单：

- 先有尺子
- 再调输入
- 再加记忆
- 最后补恢复和扩展

---

## 10. 每个阶段的完成定义

### Phase 1 Done

- 能离线跑 PR review 样本集
- 能输出可读报告
- 能对比两个版本
- 团队能用这套结果讨论“是不是变好了”

### Phase 2 Done

- 长 PR 质量明显更稳
- 同仓库 review 更贴业务和团队习惯
- 记忆已进入主链路
- 至少一个指标经评测验证提升

### Phase 3 Done

- 失败恢复不再只有 rerun
- 系统具备基本幂等和 checkpoint
- 工具扩展不会明显恶化路由复杂度
- 线上运行稳定性更强

---

## 11. 给自己排优先级时的一句话原则

以后你在这个项目上做取舍时，我建议始终用下面这条原则：

> **优先做那些能提升“可验证性、可复用性、可恢复性”的能力，而不是只让模型一次性说得更多。**

这条原则基本就能帮你区分：

- 什么是 harness engineering 的有效投入
- 什么只是短期看起来热闹的优化

---

## 12. 一句话总结

这份 roadmap 的核心逻辑是：

> 先把 PR Agent 变成“能被衡量的系统”，再把它变成“会积累经验的系统”，最后把它变成“遇到失败也能稳定恢复的系统”。

---

## 13. 当前补充进展

截至当前实现，Harness Engineering 的补齐已经从文档评估进入代码落地阶段。

| 层级 | 当前状态 | 已完成内容 | 剩余工作 |
| --- | --- | --- | --- |
| Level 1：上下文管理 | MVP 已完成 | 已增加风险排序、文件级摘要、分阶段上下文预算、工具/知识/历史经验分区注入 | 后续可加入语义压缩、按文件类型动态预算、超长 PR map-reduce |
| Level 2：工具系统 | 接近完整 | 已有 PR meta、PR diff、知识检索、历史任务查询、PR commits、PR checks、issue 背景、代码搜索、依赖/调用链上下文、跨 PR 关联等工具，并有工具调用 trace | 后续可补更精确依赖图、符号级引用定位等更深工具 |
| Level 3：执行编排 | MVP 已完成 | 已有 planner、executor、replanner、多阶段生成、强制兜底生成、阶段级 checkpoint/resume | 后续可补更细粒度 checkpoint、并行工具调用、阶段超时控制 |
| Level 4：状态与记忆 | MVP 已完成 | 已新增 repo-level 持久化 review memory，并注入审查上下文 | 后续可做记忆质量评估、记忆过期策略、按文件/模块维度记忆 |
| Level 5：评估与观测 | MVP 已完成 | 已新增离线评估数据集、指标、报告、LLM Judge、A/B 对比、回归标记、线上任务 observability trace | 后续可接 CI、线上样本采样、仪表盘和人工反馈闭环 |
| Level 6：约束与恢复 | 接近完整 | 已实现 webhook 幂等、错误分类、恢复策略矩阵、阶段失败 trace、降级上下文重试、失败后续跑、人工接管信号、任务告警出口、外部 webhook 告警发送 | 剩余更细粒度恢复策略 |

### 已经成功补充的工作量

1. **评估体系**：PR Agent 已经可以用离线样本集衡量输出质量，而不是只靠主观感觉判断。
2. **上下文治理**：长 diff 不再只是简单截断，而是先做风险排序、摘要和分阶段预算。
3. **仓库记忆**：系统已能从历史 PR 审查中沉淀 repo-level 经验，并在后续审查中复用。
4. **幂等保护**：同一个 PR head commit 的 webhook 重复触发会复用已有任务，避免重复生成。
5. **错误分类与恢复**：失败不再只记录原始异常，已能区分 GitHub API、LLM、知识检索、空 diff、未知错误，并对阶段生成失败做降级重试。
6. **checkpoint/resume**：每个生成阶段完成后会写入检查点；任务重跑时会跳过已成功阶段，只重试缺失或失败阶段。
7. **恢复策略矩阵**：GitHub API 失败会短重试，LLM 失败会降级上下文重试，知识库失败会跳过知识上下文继续，空 diff 会 fail fast。
8. **线上观测 trace**：每个任务会记录阶段耗时、工具耗时、错误分类、恢复动作、checkpoint 命中和完成阶段。
9. **GitHub 审查工具扩展**：Agent 已能主动读取 PR commits 和 PR checks，把 CI 状态与提交语义纳入审查上下文。
10. **Issue / Code Search 工具**：Agent 已能读取关联 issue 背景，并基于仓库代码搜索查找相关实现位置。
11. **依赖/调用链工具**：Agent 已能从 diff 中提取函数/类名并搜索相关实现文件，辅助判断改动波及范围。
12. **人工接管 / 告警出口**：任务会在关键失败、部分完成、多次 fallback/replan 场景下写入 `manual_handoff` 和 `alert` 信号。
13. **外部告警通道**：系统已支持把 `alert` 信号发送到外部 webhook，并内置 `generic / slack / feishu` 三种载荷格式。

### 还剩多少工作量

如果按生产级 harness 来看，当前大约完成了 **98%+** 的核心补齐工作。

剩余最值得继续做的是：

1. **线上观测闭环**：把当前 trace 指标进一步汇总到 dashboard、周期报告或告警规则里。
2. **工具系统扩展**：继续补跨 PR 关联、更精确依赖图、符号级引用定位等更深工具。
3. **更细粒度 checkpoint**：未来可把工具调用、planner、replanner 也纳入可恢复检查点。
4. **运营面板增强**：继续补图表展示、仓库对比和更细时间维度分析。
5. **深度静态分析**：补更精细依赖图、符号级引用定位和更强的代码关系分析。
