# 项目简历讲解稿

## 一、项目简介怎么讲

简历里的这句话：

> 面向团队研发协作场景，设计并实现以 GitHub PR 自动审查为核心的 Agent Harness 系统，将 PR Review 从单次模型生成升级为具备任务编排、工具增强、恢复控制、评估观测和人工接管能力的工程化 Agent Harness。

在项目里不是一句抽象概念，而是被拆成了几条明确的工程链路：

1. PR 审查不再是“拿到 diff 直接让模型输出 review”，而是一个多阶段任务。
   项目里把流程拆成 `Planner -> Executor -> Replanner -> Stage Generator -> Reporter`。对应代码主入口在 `backend/services/pr_review_agent_service.py`，提示词分别在：
   - `backend/prompts/pr_review_agent_planner.py`
   - `backend/prompts/pr_review_agent_executor.py`
   - `backend/prompts/pr_review_agent_replanner.py`
   - `backend/prompts/pr_review_agent_reporter.py`

2. Agent 不是只靠模型内部知识，而是显式接入工具和外部上下文。
   工具层放在 `backend/services/pr_review_tool_service.py`，GitHub 数据获取在 `backend/services/github_service.py`，包括 PR 基本信息、diff、commits、checks、issue、仓库代码搜索、历史任务信息等。

3. 任务不是“调完一次模型就结束”，而是有状态、有恢复、有持久化。
   任务状态和调度在 `backend/services/agent_service.py`，中间执行轨迹会写回 `AgentTask.source_payload`，阶段 checkpoint 也会保存，便于失败恢复和人工接管。

4. 不是黑盒运行，而是能看执行过程、失败原因和运行趋势。
   API 暴露在 `backend/routers/github_router.py`，可以查看任务列表、任务详情、dashboard 聚合指标、手动接管信号和告警信号。

5. 不是只优化 Prompt，而是引入离线评测闭环。
   离线 PR Review 评测模块在 `backend/evaluation/pr_review/`，可以跑数据集、打指标、做版本对比。

如果面试官问“为什么你把它叫 Harness 而不是普通 LLM 应用”，你可以回答：

> 因为这个系统的重点不是单次生成，而是围绕模型外部做了上下文治理、工具路由、任务编排、故障恢复、观测评估和人工接管，这些都属于典型的 harness engineering。

---

## 二、逐条讲解简历内容

## 1. 将 PR 审查重构为多阶段 Agent 工作流，拆分计划、执行、重规划和结果汇总，提升长 PR 场景下审查链路的稳定性与可控性

### 项目里具体怎么做

这部分最核心的实现就在 `backend/services/pr_review_agent_service.py`。

我不是直接用一个 Prompt 让模型一次性输出完整 review，而是把 PR 审查拆成四层角色：

1. `Planner`
   先根据 PR 标题、描述、文件列表和 diff 摘要判断这次 PR 的类型、风险关注点、后续步骤、是否要查团队知识。
   代码入口：`_plan_agent(...)`
   提示词：`backend/prompts/pr_review_agent_planner.py`

2. `Executor`
   不负责直接写 review，而是每轮只决定“下一步该做什么”，比如先查 diff、先查知识、还是先生成 review 阶段。
   代码入口：执行主循环中的动作决策逻辑
   提示词：`backend/prompts/pr_review_agent_executor.py`

3. `Replanner`
   如果工具结果不够、阶段生成失败、或者主循环陷入停滞，就触发重规划，重新生成 focus、后续步骤和更保守的 fallback 策略。
   代码入口：重规划相关逻辑与 `state.replans`
   提示词：`backend/prompts/pr_review_agent_replanner.py`

4. `Reporter`
   最后不重新生成审查结果，而是根据计划、工具调用、阶段产出和 fallback 轨迹，生成一份执行摘要，方便前端展示和排障。
   提示词：`backend/prompts/pr_review_agent_reporter.py`

在输出结果上，我还把内容拆成三个阶段：

1. `review`
2. `test_suggestion`
3. `unit_test`

也就是先做代码审查，再做测试建议，再做单测建议，而不是把三类内容混在一次回答里。这样做的收益是：

1. 每个阶段的目标更明确，Prompt 更稳定。
2. 某一阶段失败时不会把整单任务全部打废。
3. 可以做 checkpoint，支持断点恢复和部分重跑。
4. 更适合长 PR，因为不需要一次性把所有结论都压进一个输出。

### 你在面试里可以这样说

我把 PR 审查从单次 LLM 生成，重构成了一个有状态机特征的多阶段 Agent 工作流。模型先规划，再决策下一步动作，执行过程中如果上下文不够或者生成失败，会触发 replan，最后再汇总执行摘要。这样在长 PR 和复杂 PR 场景下，稳定性和可控性会明显好于单轮大 Prompt。

---

## 2. 设计 PR 上下文治理机制，对长 diff 进行风险排序、摘要压缩和阶段化组织，并结合团队知识与历史经验补充上下文，降低输出漂移问题

### 项目里具体怎么做

这部分主要落在 `backend/services/pr_review_agent_service.py`、`backend/services/github_service.py` 和 `backend/services/pr_review_tool_service.py`。

#### 1. 长 diff 不直接全量灌给模型，而是做预算控制

在配置里加了多组上下文预算参数，例如：

1. `pr_context_planner_diff_chars`
2. `pr_context_stage_diff_chars`
3. `pr_context_stage_summary_chars`
4. `pr_context_tool_history_chars`
5. `pr_context_knowledge_chars`
6. `pr_context_changed_files_limit`
7. `pr_context_degraded_diff_chars`
8. `pr_context_degraded_summary_chars`

也就是说，Planner 阶段、Stage 生成阶段、降级重试阶段看到的 diff 长度和摘要长度都不一样，不是“一套上下文喂到底”。

#### 2. 对 PR 文件做 reviewable diff 构造和风险优先级处理

PR 原始文件列表会先经过 GitHub 服务层处理，再构造成适合审查的 diff 文本。这个过程不是简单拼字符串，而是做了可审查视图的控制，避免无关内容把模型上下文打满。

#### 3. 同一个任务的不同阶段，看到的上下文是不同的

review 阶段更关注风险与行为变化，test_suggestion 更关注场景覆盖，unit_test 更关注测试目标、断言方向和 mock 依赖。所以阶段生成不是公用同一份输入，而是按阶段组织上下文。

#### 4. 上下文不只来自当前 PR，还会补充知识库和历史经验

有两类额外上下文被注入：

1. 团队知识
   通过 `search_review_knowledge(...)` 从知识库检索规范、经验和文档片段，再经过 `filter_relevant_chunks(...)` 过滤后注入。

2. 仓库历史经验
   通过 `build_repo_review_memory(...)` 和 `refresh_repo_review_memory(...)` 总结同仓库历史任务中的高频风险模式和测试关注点，并作为 repo-level memory 注入当前任务。

#### 5. 对历史任务做结构化提炼，而不是只展示原文

`build_repo_review_memory_from_tasks(...)` 会从历史 review、测试建议、单测建议里抽取高频关键词，归纳成：

1. 高频风险模式
2. 高频测试关注
3. 最近任务摘要

所以“历史经验补充上下文”不是简单把旧任务拼给模型，而是做了压缩和归纳。

### 你在面试里可以这样说

我做的上下文治理不是只做截断，而是把上下文预算按阶段拆开，同时把当前 PR 的 diff、文件列表、工具结果、团队知识和仓库历史经验做分层组织。这样可以减少长上下文里无关信息对输出的污染，降低结果漂移。

---

## 3. 构建代码审查工具增强链路，使 Agent 能结合 PR 变更、仓库上下文和历史任务信息完成审查推理，提升结果针对性与可解释性

### 项目里具体怎么做

这部分核心在 `backend/services/pr_review_tool_service.py`。

我把工具链分成几类：

#### 1. PR 直接上下文工具

包括：

1. PR 基本信息
2. PR diff
3. PR commits
4. PR checks
5. 关联 issue 信息

这些工具让模型不是只看到最终 patch，还能知道：

1. 这个 PR 的提交演化过程
2. 当前 CI/check 状态
3. 关联 issue 的业务背景

#### 2. 仓库上下文工具

包括：

1. `build_code_search_tool_result(...)`
2. `build_dependency_context_tool_result(...)`

这类工具会根据 diff 中新增的函数、类名、文件名去反推依赖/调用链查询，把仓库里相关实现搜出来。这样 Agent 可以判断这次修改会影响哪些已有逻辑，而不是只盯着当前 diff。

#### 3. 知识与历史任务工具

包括：

1. `search_review_knowledge(...)`
2. `list_recent_repo_tasks(...)`
3. `build_related_prs_tool_result(...)`
4. `build_repo_review_memory(...)`

这使得 Agent 可以结合团队规范、最近类似任务和历史 PR 经验来做更贴近团队场景的判断。

#### 4. 工具使用是被约束的，不是模型随意乱调

在 Planner/Executor/Replanner 的 Prompt 中，允许工具集合是白名单控制的。Executor 只能在 `use_tool / generate_stage / finish` 三种动作里选，而且不允许无意义重复调用相同工具。

这部分很重要，因为它说明这不是开放式 agent，而是一个受控工具编排系统。

### 为什么这能提升针对性和可解释性

1. 针对性
   模型能拿到 PR 之外的仓库上下文、调用链、checks 和历史经验，所以输出不容易只停留在“注意边界条件”这种空话。

2. 可解释性
   每次工具调用、参数和工具结果摘要都会写入执行轨迹。后续可以在任务详情里看到“这个结论是基于哪些工具和哪些上下文得到的”。

### 你在面试里可以这样说

我没有把工具做成一个统一的黑盒 GitHub 查询接口，而是拆成 PR 元信息、diff、checks、commits、issue、仓库代码搜索、依赖上下文和历史任务几类工具。这样模型的推理证据链更清楚，输出也更能贴合仓库真实上下文。

---

## 4. 针对模型与外部依赖不稳定问题，设计可恢复执行机制，使任务在异常场景下仍可执行、保留状态和人工接管

### 项目里具体怎么做

这部分主要在 `backend/services/pr_review_agent_service.py`、`backend/services/agent_service.py`、`backend/services/alert_service.py` 和 `backend/routers/github_router.py`。

#### 1. 先做错误分类，而不是一律按失败处理

代码里有：

1. `classify_pr_agent_error(...)`
2. `recovery_strategy_for(...)`

它会把错误区分成 GitHub API 错误、空 diff 错误、权限/未知错误等，再决定后续恢复策略。

#### 2. GitHub 上下文获取支持重试恢复

`_fetch_pr_context_with_recovery(...)` 不是拿不到 PR 数据就直接失败，而是按配置 `pr_recovery_github_attempts` 做重试，并把恢复事件写进 `fallback_events`。

#### 3. 阶段生成支持降级重试

`_generate_stage(...)` 中如果某个阶段生成失败，会记录 `stage_failed`，然后进入 `degraded_retry` 路径，用更短的 diff 和更保守的上下文再试一次。

#### 4. 阶段完成后持久化 checkpoint

`_persist_stage_checkpoint(...)` 会把阶段结果、fallback、observability、checkpoint 信息写回任务 payload。

这意味着：

1. review 已生成，后面阶段失败时，不需要完全重来。
2. 重新运行时可以识别哪些阶段已经完成。
3. 可以做 resume，而不是单纯 rerun 整单。

#### 5. 主调度层支持失败后保留部分结果

`backend/services/agent_service.py` 里不是只区分 completed/failed，还会区分 `partial_completed`。如果三个阶段里只有部分失败，已有输出不会被抹掉，而是保留成功阶段结果，并补充错误分类信息。

#### 6. 加入人工接管和告警机制

当出现关键上下文类失败、部分阶段失败、或者 fallback/replan 过多时，会生成：

1. `manual_handoff`
2. `alert`

然后通过 `send_pr_alert(...)` 发 webhook，并在任务详情和任务列表里透出接管信号。

#### 7. 做 webhook 幂等去重

`github_webhook(...)` 会按 `repo_id + pr_number + commit_sha` 检查是否已有同一 PR head commit 对应任务，避免重复创建任务。

### 你在面试里可以这样说

我做的恢复机制不是简单 try-catch，而是把恢复分成错误分类、重试、降级、checkpoint、部分完成保留、人工接管和告警几层。这样即使 GitHub API、模型输出或者上下文不足导致异常，任务也能尽量保住已有结果，并把风险显式暴露给人。

---

## 5. 建设评估与观测闭环，使 Prompt、上下文和工具策略调整能够被稳定比较、持续复盘和工程化迭代

### 项目里具体怎么做

这部分分成“线上观测”和“离线评测”两条线。

#### 1. 线上观测

在 PR Agent 主流程里，会记录：

1. `tool_calls`
2. `executed_steps`
3. `observations`
4. `replans`
5. `fallback_events`
6. `error_events`
7. `observability`

其中 `observability` 里会聚合：

1. 总耗时
2. 分阶段耗时
3. 工具调用耗时
4. 工具调用次数
5. 知识源数量
6. replan 次数
7. fallback 次数
8. checkpoint 命中情况
9. 完成阶段列表

这些数据会通过 `merge_agent_payload(...)` 写回任务，后续前端和 API 都能读。

#### 2. API 侧提供 dashboard 聚合

`backend/routers/github_router.py` 里新增了 `/dashboard`，会统计：

1. 任务数
2. 人工接管数
3. 告警数
4. checkpoint 命中数
5. 平均耗时
6. 状态分布
7. 错误类别分布
8. 恢复策略分布
9. 每日趋势
10. Top 仓库

所以不是只能看单任务，而是能从 repo / 时间维度看 PR Agent 的运行状态。

#### 3. 离线 PR Review 评测

在 `backend/evaluation/pr_review/` 下，我补了完整骨架，包括：

1. 数据集 schema
2. example dataset
3. dataset loader
4. metrics
5. judges
6. runner
7. CLI
8. compare CLI

它的目标是让 Prompt、上下文拼装逻辑和工具策略的改动可以被离线复现和对比，而不是靠感觉判断“这次是不是更好了”。

#### 4. 评测指标的思路

从文档和代码设计看，重点围绕：

1. 风险命中率
2. 输出空泛度
3. 测试建议可执行性
4. 输出结构稳定性
5. fallback / replan 等运行时指标

### 你在面试里可以这样说

我不希望这个系统变成只能靠主观体验优化的黑盒，所以一方面把运行时轨迹和恢复事件结构化落库，支持 dashboard 聚合；另一方面单独建设了 PR Review 离线评测框架，让 Prompt、上下文和工具策略的调整能做版本对比和复盘。

---

## 6. 面向团队知识问答与 PR Agent 规范检索场景，围绕召回率、上下文相关性和答案可信度重构 RAG 链路，完成数据治理、检索增强和生成约束的系统优化

### 项目里具体怎么做

这部分主要在 `backend/services/rag_service.py`，并结合 `backend/services/memory_service.py`、`backend/prompts/rag_answer.py`、`backend/prompts/rag_query_rewrite.py`。

#### 1. 检索不是单路，而是混合检索

`hybrid_retrieve(...)` 同时结合：

1. 向量检索 `vector_search(...)`
2. BM25 关键词检索 `BM25Retriever`

这样做是为了兼顾语义召回和关键词精确匹配，提升召回率，尤其适合规范文档、代码片段和术语混合场景。

#### 2. 不只取命中 chunk，还做邻接块扩展

检索结果拿到后，会按 `doc_id + filename + chunk_index` 建索引，再根据 `rag_neighbor_window` 扩展相邻 chunk。

这个设计解决的是：

1. 命中片段只有标题没有正文
2. 命中片段只有定义没有上下文
3. 规范说明被切块后语义不完整

#### 3. 检索结果还会做一次相关性过滤

`filter_relevant_chunks(...)` 不是直接把 top-k 全给生成模型，而是先让模型做一次“候选片段相关性判断”，只保留真正与问题直接相关的 chunk。

这一步的收益是降低上下文噪音，提升最终答案的相关性和稳定性。

#### 4. 生成 Prompt 强制绑定来源上下文

`build_rag_prompt(...)` 会把 chunk 按来源文件编号拼成上下文，目标是让回答明确建立在已检索内容之上，而不是让模型脱离资料自由发挥。

这本质上是在提高答案可信度。

#### 5. 会话记忆支持压缩和重写辅助

`ShortTermMemory` 里有：

1. token 近似计数
2. 历史对话压缩 `maybe_compress(...)`
3. 查询改写所需的摘要和最近轮次提取

也就是说，RAG 不只是“检索 + 回答”，还考虑了长对话下的上下文压缩与查询重写基础设施。

#### 6. 长期记忆支持去重和语义召回

`search_long_term_memories(...)` 会对用户长期记忆做 embedding 检索；`extract_and_save_memories(...)` 会从对话中抽取可沉淀信息并去重保存。

虽然这部分更偏通用对话记忆，但它体现了项目在“上下文相关性”和“个性化可信回答”上的工程思路。

### 你在面试里可以这样说

RAG 这部分我重点做的是三件事：第一，用向量检索加 BM25 做混合召回；第二，对切块结果做邻接扩展和相关性过滤，减少上下文断裂与噪音；第三，在生成侧约束回答尽量基于检索证据输出，而不是脱离资料自由生成。

---

## 三、如果面试官追问“你的技术亮点是什么”

你可以总结成下面 5 点：

1. 我把 PR Review 从单轮 Prompt 升级成了有计划、执行、重规划、汇总、恢复和观测的 Agent Harness。
2. 我做了分阶段的上下文治理，而不是只靠截断处理长 diff。
3. 我把工具链拆成了 PR、仓库、知识、历史经验几类上下文工具，增强了审查推理证据链。
4. 我设计了错误分类、降级重试、checkpoint、partial complete、人工接管和 webhook 告警，提升了系统可恢复性。
5. 我补了线上观测和离线评测，使系统优化可以被比较、复盘和持续迭代。

---

## 四、如果面试官问“你个人负责的部分是什么”

建议你按下面这种方式讲，既像负责人，也不容易显得夸大：

我主要负责的是 GitHub PR Agent 这条主链路的工程化改造，包括工作流拆分、上下文治理、工具增强、恢复机制、观测指标和离线评测骨架设计。同时我也参与了知识库问答链路的检索增强和生成约束优化，让团队规范检索和 PR Agent 的知识注入更稳定。

---

## 五、可直接压缩成简历面试版口述

这个项目本质上是一个面向团队研发协作的 GitHub PR 审查 Agent Harness。我的核心工作不是单纯写几个 Prompt，而是把 PR Review 做成了一条工程化链路。具体来说，我把 PR 审查拆成 Planner、Executor、Replanner 和 Reporter 几个角色，并把输出拆成 review、测试建议、单测建议三个阶段，解决长 PR 一次性生成不稳定的问题。

在上下文侧，我做了分阶段预算控制、diff 摘要和历史经验注入，不让模型直接吃全量长 diff；在工具侧，我补了 PR 元信息、checks、commits、issue、仓库代码搜索、依赖上下文和历史任务记忆这些能力，让审查结果更有证据链；在稳定性侧，我做了错误分类、重试、降级、checkpoint、partial complete、人工接管和 webhook 告警；在治理侧，我补了 dashboard 和离线评测框架，让 Prompt、上下文和工具策略的优化可以被稳定比较。除此之外，我还参与了 RAG 链路优化，通过混合检索、邻接块扩展、相关性过滤和生成约束，提升团队知识问答和 PR Agent 规范检索的召回率、相关性和可信度。
