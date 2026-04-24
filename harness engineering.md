# Harness Engineering 视角下的 GitHub PR Agent 评估

## 1. 先说结论

我现在对这个仓库里的 GitHub PR Agent 的判断是：

- 它已经不是单纯的 Prompt 调用器
- 它已经具备比较明确的 harness 雏形
- 它最强的是 **执行编排（orchestration）**
- 它次强的是 **工具系统（tooling）** 和 **约束/兜底（guardrails & recovery）**
- 它目前相对偏弱的是 **状态/记忆（state & memory）** 和 **评估体系（evaluation）**

更准确地说，它现在属于：

> 一个已经进入 Harness Engineering 早中期形态的 Workflow Agent

而不是：

- 纯 Prompt Agent
- 完整成熟的 Agent Platform
- 具备强自学习能力的自治 Agent

---

## 2. 什么是 Harness Engineering

如果把大模型 Agent 看成一个“会推理的核心”，那么 harness 就是包在这个核心外面的工程层。  
它负责解决的不是“模型会不会说”，而是：

- 给模型什么上下文
- 允许模型调用什么能力
- 调用顺序怎么控制
- 状态怎么保存
- 如何判断执行效果
- 如果失败怎么兜底

所以从工程角度看：

> **Harness Engineering = 把模型能力包装成稳定、可控、可观测、可恢复的系统工程。**

---

## 3. 六层分法是否合理

你提到的视频把 harness 分成六层：

1. 上下文管理
2. 工具系统
3. 执行编排
4. 状态与记忆
5. 评估与观测
6. 约束与恢复

我认为这个分法 **是合理的，而且很适合工程实践**。

它不是唯一标准，但非常适合作为你现在评估 PR Agent 的框架。原因是：

- 它覆盖了 Agent 从输入到执行到治理的完整闭环
- 它既能看架构，也能看代码落点
- 它非常适合用来做“能力盘点”和“后续演进路线图”

唯一需要注意的是：

- `状态与记忆`
- `约束与恢复`

这两层在实际工程里有时会交叉，比如“失败后从哪个状态恢复”既像状态问题，也像恢复问题。  
但这不影响这套分层本身的实用性。

---

## 4. 六层定义

| 层级 | 名称 | 核心问题 | 典型能力 |
| --- | --- | --- | --- |
| Level 1 | 上下文管理 | 给模型看什么 | 输入选择、裁剪、摘要、排序、拼装 |
| Level 2 | 工具系统 | 模型能动什么 | 工具定义、参数约束、工具边界、工具返回结构 |
| Level 3 | 执行编排 | 下一步做什么 | Planner、Executor、状态机、循环控制、阶段推进 |
| Level 4 | 状态与记忆 | 系统记住什么 | 任务状态、执行轨迹、短期状态、长期记忆、跨任务复用 |
| Level 5 | 评估与观测 | 怎么知道好不好 | 日志、trace、指标、离线评测、回归测试、线上监控 |
| Level 6 | 约束与恢复 | 如何防失控与失败 | 白名单、格式约束、回退规则、重试、重规划、断点恢复 |

---

## 5. 你的 PR Agent 六层能力总表

| 层级 | 当前结论 | 成熟度判断 | 你现在的表现 |
| --- | --- | --- | --- |
| Level 1 上下文管理 | 已实现，但偏静态 | 中等 | 能拼装 PR 元信息、Diff、工具结果、知识检索结果，但还没有动态上下文预算 |
| Level 2 工具系统 | 已实现，结构比较清楚 | 中上 | 已有明确工具边界和允许工具集合，属于比较像样的 agent tooling |
| Level 3 执行编排 | 实现最好 | 较强 | 已有 Planner / Executor / Replanner / Reporter，且有主循环和阶段推进 |
| Level 4 状态与记忆 | 部分实现 | 中下 | 有任务状态和 trace 持久化，但缺少跨任务记忆与经验复用 |
| Level 5 评估与观测 | 部分实现，观测强于评估 | 中下 | 有日志、trace、前端执行轨迹，但缺少 PR Agent 专属评测框架 |
| Level 6 约束与恢复 | 已实现一部分 | 中等 | 有 JSON 约束、工具白名单、规则兜底、重规划和强制补阶段 |

---

## 6. 详细矩阵：哪些理念实现了，哪些没实现

| 层级 | Harness 理念 | 你是否实现 | 代码依据 | 我的判断 |
| --- | --- | --- | --- | --- |
| Level 1 | 上下文不是全塞，应该被组织 | 已实现 | `backend/services/pr_review_agent_service.py:150` `backend/services/pr_review_agent_service.py:188` | 你会把 PR 标题、描述、文件列表、工具结果、知识片段、diff 组织成不同阶段输入 |
| Level 1 | 上下文需要做预算控制 | 部分实现 | `backend/services/pr_review_agent_service.py:119` `backend/services/github_service.py:126` | 你有截断，但还不是 token-aware 的动态预算系统 |
| Level 1 | 不同阶段应该使用不同上下文视图 | 已实现 | `backend/services/pr_review_agent_service.py:168` `backend/services/pr_review_agent_service.py:188` | planner、executor、stage generation 使用的上下文结构不同 |
| Level 1 | 长上下文应支持摘要、重排、按需取回 | 未充分实现 | `backend/services/memory_service.py:104` | 这套能力存在于 chat memory，不在 PR Agent 主链路里 |
| Level 2 | 工具要有清晰边界 | 已实现 | `backend/prompts/pr_review_agent_planner.py:13` `backend/services/pr_review_tool_service.py:17` | `get_pr_meta`、`get_pr_diff`、`search_review_knowledge`、`list_recent_repo_tasks` 边界清晰 |
| Level 2 | 工具输入输出要稳定 | 已实现 | `backend/services/pr_review_tool_service.py:17` | 每个工具都返回结构化文本结果，便于拼接给模型 |
| Level 2 | 工具集合应该白名单化 | 已实现 | `backend/prompts/pr_review_agent_executor.py:13` | 工具集合被明确限制，不是开放调用 |
| Level 2 | 工具路由要真正参与执行闭环 | 部分实现 | `backend/services/pr_review_agent_service.py:373` | 有工具决策，但 `suggested_tools` 更多像计划产物，参与度还不深 |
| Level 3 | 先计划，再执行 | 已实现 | `backend/services/pr_review_agent_service.py:284` | 先 `plan` 再进入执行循环 |
| Level 3 | 执行应该是状态机，而不是一次性 Prompt | 已实现 | `backend/services/pr_review_agent_service.py:498` | 有明确 loop、action、stage、finish |
| Level 3 | 编排应分角色提示词 | 已实现 | `backend/prompts/pr_review_agent_planner.py:1` `backend/prompts/pr_review_agent_executor.py:1` `backend/prompts/pr_review_agent_replanner.py:1` `backend/prompts/pr_review_agent_reporter.py:1` | 这是典型 harness 风格 |
| Level 3 | 编排要能检测停滞并调整 | 已实现 | `backend/services/pr_review_agent_service.py:524` | 有 stagnant rounds 检测和 replan |
| Level 4 | 系统要保存任务状态 | 已实现 | `backend/models/agent_task.py:6` `backend/services/agent_service.py:23` | 有 queued/running/completed/failed/partial_completed |
| Level 4 | 系统要保存执行轨迹 | 已实现 | `backend/services/pr_review_agent_service.py:608` | plan、tool_calls、replans、fallback_events 都持久化了 |
| Level 4 | 状态要可被前端查看 | 已实现 | `backend/routers/github_router.py:131` `frontend/src/pages/GithubAgentPage.tsx:193` | 这点做得不错，已经有 trace UI |
| Level 4 | 系统应具备跨任务记忆 | 未实现 | `backend/services/pr_review_tool_service.py:60` | 虽能看最近任务列表，但没有把历史经验真正注入当前决策 |
| Level 4 | 系统应具备长期经验沉淀 | 未实现 | `backend/services/session_store.py:17` | chat 有 memory，PR Agent 没接这套能力 |
| Level 5 | 系统要可观测 | 已实现 | `backend/services/agent_service.py:38` `backend/services/pr_review_agent_service.py:516` | 已有日志和执行摘要 |
| Level 5 | 用户要能看到执行路径 | 已实现 | `frontend/src/pages/GithubAgentPage.tsx:202` | plan/tool/replan/fallback 都能在前端看 |
| Level 5 | 要有离线评测能力 | 未实现（针对 PR Agent） | `backend/evaluation/README.md:1` | 仓库有 evaluation，但当前是面向 RAG，不是 PR Review Agent |
| Level 5 | 要有质量回归基线 | 未实现 | 无专门文件 | 没看到 review 误报率、漏报率、具体性评分等体系 |
| Level 6 | 模型输出要被约束 | 已实现 | `backend/prompts/pr_review_agent_executor.py:24` `backend/prompts/pr_review_agent_planner.py:8` | 强制 JSON、限制字段和动作 |
| Level 6 | 系统要有规则优先兜底 | 已实现 | `backend/services/pr_review_agent_service.py:126` `backend/services/pr_review_agent_service.py:373` | 先 rule fallback，再给模型决策 |
| Level 6 | 失败后要有恢复动作 | 已实现 | `backend/services/pr_review_agent_service.py:332` `backend/services/pr_review_agent_service.py:592` | 有 replan 和强制补生成 |
| Level 6 | 工具重复调用要受控 | 已实现 | `backend/services/pr_review_agent_service.py:406` | 已有 `_has_tool_call` 去重 |
| Level 6 | 应支持断点恢复/幂等执行 | 未充分实现 | `backend/routers/github_router.py:156` | 现在更像 rerun 新任务，不是从中断点继续恢复 |

---

## 7. 分层详细评价

### Level 1：上下文管理

### 你已经实现的理念

- 不同执行阶段使用不同 prompt 和不同上下文视图
- 把 PR 元信息、文件列表、工具结果、知识片段和 diff 组合成结构化输入
- 有最基础的截断能力，避免超长内容直接灌给模型

### 你还没实现好的理念

- 没有真正的 token budget manager
- 没有按“重要性”重排 diff 片段
- 没有按文件风险动态筛选上下文
- 没有把历史失败案例或历史 review 经验作为可检索上下文引入

### 客观评价

你这层已经具备 **context assembly**，但还没进入 **context optimization**。

换句话说：

- 你已经会“拼上下文”
- 但还没有做到“精算上下文”

这也是很多 Agent 系统从能跑到稳定之间的分水岭。

---

### Level 2：工具系统

### 你已经实现的理念

- 工具边界比较清晰
- 工具名可读性不错
- 工具白名单明确
- 工具和编排逻辑分离
- PR 元信息、Diff、知识检索、历史任务查询属于不同职责

### 你还没实现好的理念

- `suggested_tools` 没真正深度参与调度策略
- 工具返回仍以文本为主，缺少更细粒度结构化 schema
- 没有工具质量监控，比如“哪个工具最常无效”
- 没有更丰富的 PR 专属工具，例如：
  - 获取 reviewer comments
  - 获取历史提交摘要
  - 获取关联 issue / commit
  - 获取测试文件变更映射

### 客观评价

这一层是你现在比较接近 “工程化 harness” 的地方。  
尤其是你没有把所有外部能力糊成一个大 `github_tool`，这点很好。

---

### Level 3：执行编排

### 你已经实现的理念

- 有 planner
- 有 executor
- 有 replanner
- 有 reporter
- 有循环控制
- 有阶段推进
- 有停滞检测
- 有结束条件

### 你还没实现好的理念

- executor 的模型决策空间仍然比较窄
- 还没有更细粒度的 action taxonomy，例如：
  - ask_human
  - skip_stage
  - retry_tool
  - degrade_mode
- 还没有并行工具调用
- 还没有真正的 DAG 或 task graph

### 客观评价

这层是你现在最强的部分。  
它已经明显体现出 harness engineering 的核心思想：

> 模型不直接等于系统，模型只是被系统编排的一环。

这点在 `backend/services/pr_review_agent_service.py:498` 体现得很明显。

---

### Level 4：状态与记忆

### 你已经实现的理念

- 有任务状态
- 有阶段状态
- 有执行步骤记录
- 有工具调用记录
- 有重规划记录
- 有 fallback 记录
- 有结果持久化
- 有前端可视化消费

### 你还没实现好的理念

- 没有跨 PR 的长期经验记忆
- 没有 repo-level 审查偏好记忆
- 没有“这类 PR 以前经常漏什么”的经验注入
- 没有把人工 rerun、人工修正、人工采纳结果沉淀回系统

### 客观评价

你这层实现的是 **state tracking**，不是 **memory intelligence**。

也就是说：

- 你能记录发生过什么
- 但还不能把这些记录转化成未来决策能力

这是下一阶段很值得补的层。

---

### Level 5：评估与观测

### 你已经实现的理念

- 日志存在
- 执行 trace 存在
- 前端可视化存在
- 任务详情 API 存在
- 用户可以看到计划、工具、replan、fallback

### 你还没实现好的理念

- 没有 PR Agent 专属 benchmark
- 没有 review 质量评分体系
- 没有版本对比评估
- 没有误报 / 漏报 / 空泛度 / 具体性指标
- 没有基于历史任务沉淀的数据分析面板

### 客观评价

你现在更像是：

- **有 tracing**
- **有 debugging**

但还不是：

- **有 evaluation**
- **有 quality governance**

这是很多 Agent 项目会卡住的地方。  
因为系统“能看见”不等于系统“能量化优化”。

---

### Level 6：约束与恢复

### 你已经实现的理念

- Planner / Executor / Replanner 都有严格输出约束
- 动作集合是受限的
- 工具集合是受限的
- 阶段集合是受限的
- 有 rule-first fallback
- 有失败后的 replan
- 有最终强制补阶段
- 有重复工具调用去重

### 你还没实现好的理念

- 没有更细粒度失败分类
- 没有针对 GitHub API / LLM / 知识检索分别制定恢复策略
- 没有断点续跑
- 没有真正的 checkpoint resume
- 没有幂等键与 webhook 去重策略

### 客观评价

这一层你已经有明显的 harness 意识了。  
但目前更偏：

- “失败了以后不要完全崩”

还没有完全进入：

- “失败后如何以最小代价恢复到正确轨道”

---

## 8. 你的 PR Agent 已经实现了哪些 Harness Engineering 理念

### 已明显实现

| 理念 | 是否实现 | 说明 |
| --- | --- | --- |
| 模型输出不应直接裸奔 | 已实现 | 有 JSON 约束、动作白名单、阶段白名单 |
| 工具应与 Prompt 解耦 | 已实现 | 工具实现独立在 service 中 |
| Agent 应该是流程，而不是单次调用 | 已实现 | 存在完整执行循环 |
| 失败不能直接崩溃，应有 fallback | 已实现 | 有 replan、force generate、异常兜底 |
| 系统应保留 trace 便于排障 | 已实现 | task source_payload 中保存 agent_trace |
| 前端应能承接执行轨迹 | 已实现 | GitHub Agent 页面可展示 plan/tool/replan/fallback |

### 只实现了一半

| 理念 | 当前状态 | 说明 |
| --- | --- | --- |
| 上下文应精细化治理 | 部分实现 | 已拼装，但未动态优化 |
| 状态应转化为记忆 | 部分实现 | 已记录，但未用于未来任务 |
| 工具调用应由策略系统驱动 | 部分实现 | 已有策略，但调度深度有限 |
| 观测应服务质量优化 | 部分实现 | 有 trace，无完整质量指标 |

### 目前还没实现

| 理念 | 当前状态 | 说明 |
| --- | --- | --- |
| 通过评测集驱动 Prompt/Agent 演化 | 未实现 | 当前 PR Agent 无离线评测集 |
| 通过历史反馈形成 repo-level 审查偏好 | 未实现 | 没有经验回流 |
| 从中断点恢复执行而不是整体重跑 | 未实现 | 当前是 rerun new task |
| 形成真正的持续优化闭环 | 未实现 | 还没有 metrics -> diagnosis -> tuning 的系统链路 |

---

## 9. 如果按成熟度打分

| 层级 | 分数 | 评价 |
| --- | --- | --- |
| Level 1 上下文管理 | 6.5 / 10 | 已有基础组织能力，但缺少动态优化 |
| Level 2 工具系统 | 7.5 / 10 | 边界清楚，结构不错，但还不够丰富 |
| Level 3 执行编排 | 8 / 10 | 目前最强，已经明显具备 harness 特征 |
| Level 4 状态与记忆 | 5.5 / 10 | 有状态，无强记忆 |
| Level 5 评估与观测 | 4.5 / 10 | 有观测，无完整评估 |
| Level 6 约束与恢复 | 6.5 / 10 | 有 guardrail 和兜底，但恢复能力还不够深 |

---

## 10. 一个更准确的总评

如果让我用一句话评价你现在这个 PR Agent：

> 它已经具备了比较明确的 harness engineering 结构，尤其在执行编排、工具边界和失败兜底上表现不错；但它还没有建立起成熟 harness 最关键的两块能力：**跨任务记忆** 和 **系统化评估闭环**。

换句话说，它现在已经完成了：

- 从“Prompt 驱动”
- 走向“Workflow Harness 驱动”

但还没完成：

- 从“能运行”
- 走向“能持续优化”

---

## 11. 我最建议优先补的三层

### 第一优先级：补 Level 5 评估

因为没有评估，你很难判断：

- 哪个 Prompt 版本更好
- 哪种 replan 更有效
- 哪个工具真正有价值
- 现在输出的问题是“空泛”还是“误报”

建议补的内容：

1. 建立 PR review 评测样本集
2. 设计 review 质量指标
3. 支持版本对比
4. 做误报/漏报分析

---

### 第二优先级：补 Level 4 记忆

建议做 repo-level 或 team-level 经验沉淀，例如：

- 常见风险模式
- 过去高频漏报点
- 团队更关注的审查维度
- 某仓库的测试规范偏好

这样你的 Agent 才会越来越像“懂这个团队”的 Agent。

---

### 第三优先级：补 Level 6 恢复工程化

建议补：

1. webhook 幂等去重
2. 工具失败分类恢复
3. checkpoint / resume
4. 更细粒度的 degrade mode

---

## 12. 最后的判断

### 你的六层理解是否成立？

成立，而且适合继续沿用。

### 你的 PR Agent 现在是否已经体现 Harness Engineering 思想？

是，已经体现了，而且体现得最明显的是：

- 编排不是单轮 Prompt
- 工具不是大杂烩
- 失败不是直接结束
- 执行过程有 trace

### 目前最大的缺口是什么？

不是 Prompt 本身，而是：

- **评估闭环**
- **经验记忆**
- **恢复工程化**

### 所以应该怎么定义你当前这个系统？

我认为最准确的定义是：

> **一个具备明确 workflow harness 雏形的 GitHub PR Review Agent。**

---

## 13. 下一阶段路线图（按六层拆解）

这一部分不是再抽象评价，而是把“下一步应该补什么”落到更具体的工程动作上。

### 路线图总表

| 层级 | 当前短板 | 建议目标 | 优先级 | 推荐代码入口 |
| --- | --- | --- | --- | --- |
| Level 1 | 上下文拼得出来，但不够精算 | 建立 token-aware 上下文预算和风险排序 | 高 | `backend/services/pr_review_agent_service.py:150` `backend/services/github_service.py:126` |
| Level 2 | 工具够用，但不够丰富 | 扩展 PR 专属工具并结构化返回 | 中 | `backend/services/pr_review_tool_service.py:17` `backend/prompts/pr_review_agent_executor.py:13` |
| Level 3 | 编排较强，但动作类型偏少 | 让 action taxonomy 更细，支持更灵活决策 | 中 | `backend/services/pr_review_agent_service.py:373` `backend/prompts/pr_review_agent_executor.py:31` |
| Level 4 | 只有状态，没有经验沉淀 | 建 repo-level 和记忆回流机制 | 高 | `backend/services/pr_review_tool_service.py:60` `backend/services/pr_review_agent_service.py:608` |
| Level 5 | 有 trace，无评测体系 | 建 PR Review benchmark 和质量指标 | 最高 | `backend/evaluation/README.md:1` |
| Level 6 | 有兜底，无工程化恢复 | 做失败分类、幂等、checkpoint 和 resume | 高 | `backend/services/pr_review_agent_service.py:332` `backend/routers/github_router.py:180` |

---

## 14. 每一层怎么改，为什么改

### Level 1 路线图：从“拼上下文”升级到“治理上下文”

### 建议目标

让 PR Agent 不只是把 diff 拼进去，而是根据风险、长度、阶段来动态组织上下文。

### 建议动作

1. 引入 token-aware budget
   - 对 `pr_title`
   - `pr_body`
   - `changed_files`
   - `tool outputs`
   - `knowledge snippets`
   - `diff`
   分别设置预算，而不是简单字符串截断

2. 做 diff 风险排序
   - 优先展示：
     - 核心业务文件
     - 鉴权/安全相关文件
     - 状态变更和持久化相关文件
     - 大 patch 文件

3. 按阶段构造上下文模板
   - review 阶段偏功能与风险
   - test_suggestion 阶段偏分支和异常路径
   - unit_test 阶段偏函数入口、依赖和 mock 信息

4. 为长 diff 加摘要层
   - 先生成每个文件的 change summary
   - 再将 summary 作为中间上下文层供后续阶段消费

### 推荐改造位置

- `backend/services/pr_review_agent_service.py:150`
- `backend/services/pr_review_agent_service.py:188`
- `backend/services/github_service.py:126`

### 预期收益

- 降低长 PR 的信息淹没
- 提高输出具体性
- 降低“看了很多但其实没看到重点”的问题

---

### Level 2 路线图：从“有工具”升级到“工具可治理”

### 建议目标

让工具系统从可用走向可扩展、可评估、可复用。

### 建议动作

1. 扩展 PR 专属工具
   - `get_pr_review_comments`
   - `get_pr_commits`
   - `get_related_issue_context`
   - `get_changed_test_files`
   - `map_code_to_test_targets`

2. 工具返回从纯文本升级为“结构化 + 预览文本”
   - 给模型看的仍可保留文本
   - 但系统内部应该拿到结构化 payload，方便前端和评估模块复用

3. 给工具调用建立质量统计
   - 调用次数
   - 产出是否被实际使用
   - 哪些工具常返回低价值信息

4. 让 `suggested_tools` 真正参与调度
   - planner 不只是输出建议
   - executor 初始路由应优先参考 planner 的 suggested tools

### 推荐改造位置

- `backend/services/pr_review_tool_service.py:17`
- `backend/services/pr_review_agent_service.py:284`
- `backend/services/pr_review_agent_service.py:413`
- `backend/prompts/pr_review_agent_executor.py:31`

### 预期收益

- 工具系统更容易演进
- 工具价值可以被量化
- 更适合以后接 MCP 或外部系统工具

---

### Level 3 路线图：从“流程 Agent”升级到“更细粒度控制器”

### 建议目标

保留现有 Planner / Executor / Replanner 的架构优势，同时让 action 语义更丰富。

### 建议动作

1. 扩展 action taxonomy
   - `use_tool`
   - `generate_stage`
   - `retry_tool`
   - `degrade_mode`
   - `skip_stage`
   - `finish`

2. 区分“阶段生成失败”和“上下文不足”
   - 当前很多失败最终都会回到补生成
   - 可以把“先补上下文再生成”与“直接降级生成”分开

3. 支持轻量并行
   - 例如知识检索和最近任务读取可并行
   - 这对吞吐和响应时间会有帮助

4. 为执行循环增加明确停止原因
   - 正常完成
   - 重规划后仍停滞
   - 关键工具失败
   - 降级完成

### 推荐改造位置

- `backend/services/pr_review_agent_service.py:373`
- `backend/services/pr_review_agent_service.py:498`
- `backend/prompts/pr_review_agent_executor.py:31`
- `backend/prompts/pr_review_agent_replanner.py:19`

### 预期收益

- 决策更透明
- 失败路径更清楚
- 后续更容易做线上问题分析

---

### Level 4 路线图：从“状态记录”升级到“经验记忆”

### 建议目标

让系统不只是记录这次做了什么，而是让下一次 PR 审查也变得更聪明。

### 建议动作

1. 建 repo-level 审查记忆
   - 常见风险类型
   - 过去高频误报点
   - 团队偏好的审查重点
   - 该仓库常用测试框架

2. 将人工反馈回流为记忆
   - rerun 原因
   - 人工采纳/驳回的 review 点
   - 最终修复的问题类别

3. 将历史任务摘要化
   - 不只是列最近任务
   - 而是提炼“最近 20 个 PR 中最常见的风险模式”

4. 让记忆进入 planner 或 stage prompt
   - 作为 `repo_review_memory`
   - 或作为 `team_review_preferences`

### 推荐改造位置

- `backend/services/pr_review_tool_service.py:60`
- `backend/services/pr_review_agent_service.py:188`
- `backend/services/pr_review_agent_service.py:608`
- `backend/models/agent_task.py:18`

### 预期收益

- 提高审查贴团队风格的能力
- 降低重复犯错
- 让 Agent 真正具备“仓库经验”

---

### Level 5 路线图：从“可看见”升级到“可优化”

### 建议目标

给 PR Agent 建独立评测框架，让后续 Prompt、工具、编排修改都有可比性。

### 建议动作

1. 建 PR Review 离线样本集
   - 输入：PR title、body、changed files、diff、必要上下文
   - 标注：高风险问题、测试缺口、建议合并结论

2. 定义评测指标
   - 问题具体性
   - 风险命中率
   - 误报率
   - 漏报率
   - 测试建议可执行性
   - 输出空泛度

3. 做版本对比
   - prompt A vs prompt B
   - 规则路由前后
   - 是否使用知识检索

4. 建 trace 到 quality 的分析链路
   - 哪些 fallback 最常出现
   - 哪类 PR 最容易失败
   - 哪个阶段最容易输出空话

### 推荐改造位置

- `backend/evaluation/README.md:1`
- `backend/evaluation/runner.py`
- `backend/evaluation/metrics.py`
- 可新增 `backend/evaluation/pr_review/`

### 预期收益

- 可以真正比较“改完之后有没有变好”
- 能把 Agent 优化从经验主义变成数据驱动
- 这是后续所有治理动作的基础设施

---

### Level 6 路线图：从“兜底”升级到“恢复工程”

### 建议目标

让系统不只是“失败后补一下”，而是具备更明确的恢复策略。

### 建议动作

1. 建失败分类
   - GitHub API 失败
   - LLM 输出格式失败
   - 知识检索失败
   - 阶段生成失败
   - 状态持久化失败

2. 针对不同失败采取不同恢复
   - API 失败：重试或降级
   - JSON 失败：回退到 rule path
   - 检索失败：跳过知识层继续主流程
   - 生成失败：切 compact prompt 或更小上下文

3. 增加 webhook 幂等去重
   - 防止同一 PR synchronize 重复创建任务

4. 引入 checkpoint / resume
   - 保存当前已完成阶段
   - 失败后从未完成阶段继续
   - 而不是 rerun 整个任务

### 推荐改造位置

- `backend/services/pr_review_agent_service.py:70`
- `backend/services/pr_review_agent_service.py:332`
- `backend/services/pr_review_agent_service.py:592`
- `backend/routers/github_router.py:180`
- `backend/services/agent_service.py:23`

### 预期收益

- 降低重复运行成本
- 降低外部依赖波动对主流程的影响
- 更接近真正生产级 harness

---

## 15. 一个现实可行的三阶段演进计划

如果不想一次改太大，我建议按下面三阶段推进。

### Phase 1：补评估与观测闭环

目标：

- 先知道系统哪里好、哪里差

优先做：

1. PR review 离线样本集
2. review 质量指标
3. trace 统计
4. Prompt 版本对比

为什么最先做：

- 没有评估，后面很多优化都无法证明价值

---

### Phase 2：补上下文治理和记忆

目标：

- 让长 PR 和重复性问题表现更稳

优先做：

1. token budget
2. 风险文件排序
3. repo-level 经验记忆
4. 历史任务摘要注入

为什么第二做：

- 这两层能直接改善输出质量，但需要评估体系来验证收益

---

### Phase 3：补恢复工程和工具扩展

目标：

- 让系统更稳、更适合长期运行

优先做：

1. 幂等去重
2. 失败分类恢复
3. checkpoint / resume
4. 新增 PR 专属工具

为什么第三做：

- 当前系统已能跑，恢复工程是“上线稳定性增强项”

---

## 16. 给团队/老板看的汇报版摘要

下面这段可以直接改一改拿去汇报。

### 简版汇报口径

目前这个 GitHub PR Agent 已经不属于简单的 Prompt 自动生成，而是具备了初步的 Harness Engineering 结构。  
它已经实现了多阶段执行编排、工具白名单、执行轨迹记录和失败兜底，说明系统已经从“单轮模型调用”走向“受控工作流 Agent”。

但从成熟度看，当前系统仍主要停留在：

- 有流程
- 有工具
- 有 trace

还没有完全进入：

- 有长期记忆
- 有系统评测
- 有恢复工程

因此，下一阶段最关键的工作，不是继续单纯打磨 Prompt，而是补齐三类基础设施：

1. PR Agent 专属评估体系
2. repo-level 经验记忆
3. 更工程化的失败恢复机制

### 管理者视角版

如果从研发治理角度评价，这个 PR Agent 已经具备原型级到早期产品级之间的工程基础。  
它最大的优点是执行链路清楚，工具边界清晰，失败不会直接失控。  
它最大的短板是缺少可量化评估和长期经验积累，因此后续优化还比较依赖人工判断。

一句话总结：

> 这个系统已经具备 workflow harness 雏形，但还没有形成完整的 quality loop 和 memory loop。

---

## 17. 给你自己的定位建议

如果你后面要继续讲这个项目，我建议你这样描述，而不是只说“我做了一个 PR Review Agent”。

更好的说法是：

> 我做的是一个面向 GitHub PR 审查场景的 workflow-style agent harness。  
> 它已经具备计划、执行、重规划、结果汇总、工具调用、状态落库和执行轨迹可视化能力；当前正在从“可运行”阶段往“可评估、可记忆、可恢复”阶段演进。

这个说法的好处是：

- 比“Prompt 工程”更高级
- 比“AGI Agent”更务实
- 更符合你代码现在真实达到的层次

---

## 18. 当前代码落地后的客观更新

在本轮补充后，PR Agent 的 Harness Engineering 成熟度有明显提升：

- **Level 1 上下文管理**：已从“直接塞 diff”升级为“风险排序 + 文件摘要 + 分阶段预算 + 历史经验注入”。
- **Level 4 状态与记忆**：已从“只记录单次任务 trace”升级为“持久化 repo-level review memory”。
- **Level 5 评估与观测**：已从“缺少系统评估”升级为“有离线样本集、指标、报告、LLM Judge、A/B 对比和线上任务 observability trace”。
- **Level 6 约束与恢复**：已开始从“失败后整体报错”升级为“幂等去重 + 错误分类 + 恢复策略矩阵 + 阶段降级重试 + checkpoint/resume”。

因此，之前“还没有完全进入长期记忆、系统评测、恢复工程”的判断需要更新为：

> 当前已经具备长期记忆、系统评测、阶段级恢复、错误类型恢复策略和任务级观测 trace 的 MVP；但 dashboard/告警闭环、人工接管和更细粒度工具恢复仍未完成。

### 当前剩余短板

| 短板 | 影响 | 建议优先级 |
| --- | --- | --- |
| 线上观测未完全产品化 | 任务级 trace、alert、manual_handoff、webhook 告警、告警去重和带时间筛选/趋势统计的 dashboard 已具备，但还缺图表展示 | 低 |
| 工具系统仍未完整 | PR Agent 已能读取 checks、commit、issue 背景、代码搜索、轻量调用链上下文和跨 PR 关联，但还缺更精确依赖图与符号级引用定位 | 低 |
| checkpoint 粒度仍偏阶段级 | 当前能复用已生成内容，但工具调用和 planner 还未独立恢复 | 中 |
| 人工接管仍偏轻量 | 已有 manual_handoff 信号和 webhook 告警，但还没有完整的人审工作台或审批流 | 中 |

### 当前更准确的一句话评价

> 这个 PR Agent 已经不是简单 workflow harness，而是具备 evaluation loop、context loop、memory loop 和初步 recovery loop 的 PR review harness；下一步重点应从“补基础能力”转向“提升恢复深度和线上闭环”。
