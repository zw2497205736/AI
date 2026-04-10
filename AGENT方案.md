# PR Review Agent 落地方案

## 目标

当前项目已经具备：

- GitHub 仓库接入
- Webhook 触发
- PR 自动审查任务
- Code Review / 测试建议 / 单元测试建议三阶段输出
- 团队知识库问答
- ChatAgent 与平台内工具调用

但 GitHub PR 自动审查目前更接近“固定工作流”，还不够像一个完整的 Agent。

本方案的目标是：

- 在尽量复用现有能力的前提下
- 将 GitHub PR 自动审查升级为一个更符合业界常见模式的 `PR Review Agent`
- 让项目中真正出现一个可讲、可展示、可落地的完整 Agent 模块

## 为什么选 PR 自动审查做 Agent

相比聊天模块，PR 自动审查更适合做成经典 Agent，原因有三点：

1. 任务目标明确
   输入是一个 PR，输出是审查结果，边界清晰

2. 天然需要规划和工具调用
   不同 PR 的改动类型不同，审查重点也不同，适合先规划再执行

3. 和项目现有能力复用度高
   已有 GitHub 接入、Diff 拉取、知识库、任务系统，只需要把固定链路升级为 Agent 调度

## 业界常见的 Agent 结构

对于你这个项目，最适合采用的是单 Agent、多步骤、带状态的经典结构，而不是一上来做多 Agent。

推荐结构：

```text
PR Event / Manual Trigger
-> Planner
-> Tool Executor
-> State Store
-> Review Step Executor
-> Replan / Continue
-> Final Reporter
```

对应到你的项目里，就是：

1. 接收到 PR 任务
2. Planner 先判断本次 PR 的改动重点
3. Agent 按需调用 GitHub / 知识库 / 历史任务工具
4. 将工具结果写入状态
5. 分步骤完成 Review、测试建议、单元测试建议
6. 汇总成前端展示结果

## 最适合你项目的 Agent 定义

建议把这个模块定义为：

- `PR Review Agent`
- 或 `GitHub PR 审查 Agent`

严谨说法：

> 一个面向研发协作场景的单 Agent 审查模块，能够基于 PR 内容自主规划审查步骤，并结合 GitHub 信息、团队知识和历史任务上下文生成结构化审查结果。

这个定义比较稳，不会吹过头。

## 模块边界

这个 Agent 只负责一件事：

- 围绕一个 PR，完成动态审查

它不负责：

- 仓库接入
- Webhook 配置
- 用户登录
- 文档上传
- 普通聊天问答

这样边界清晰，后面实现不会乱。

## 推荐的最小可行架构

### 1. Planner

作用：

- 读取 PR 标题、描述、文件列表、Diff 摘要
- 判断本次 PR 属于什么类型
- 决定优先审查哪些方面

Planner 的输出不是最终审查结果，而是一份计划，例如：

```json
{
  "pr_type": "backend_api_change",
  "focus": [
    "接口兼容性",
    "异常处理",
    "测试覆盖"
  ],
  "steps": [
    "获取 PR 文件和 Diff",
    "检查是否命中团队规范",
    "生成代码审查结论",
    "生成测试建议",
    "生成单元测试建议"
  ]
}
```

### 2. Tool Layer

Agent 不应直接在 Prompt 里“假装知道”所有东西，而是要通过工具拿上下文。

建议优先保留 4 类工具：

- GitHub PR 工具
  - 获取 PR 基本信息
  - 获取 PR 文件列表
  - 获取 PR Diff

- 团队知识工具
  - 查询代码规范
  - 查询测试规范
  - 查询历史经验文档

- 平台任务工具
  - 查询历史类似任务
  - 查询同仓库最近审查记录

- 仓库上下文工具
  - 获取仓库名称、分支、默认分支等基础信息

第一版不需要太多工具，够用就行。

### 3. Agent State

Agent 必须有状态，不然就只是“连调几次模型”。

建议定义一个状态对象，至少包括：

- `task_id`
- `repo_id`
- `pr_number`
- `pr_title`
- `pr_body`
- `changed_files`
- `diff_excerpt`
- `plan`
- `executed_steps`
- `tool_outputs`
- `review_result`
- `testing_result`
- `unit_test_result`
- `final_summary`

这个状态建议统一由 `pr_review_agent_service.py` 管理。

### 4. Executor

执行器负责循环：

1. 看当前计划和状态
2. 判断下一步做什么
3. 如果需要，调用工具
4. 更新状态
5. 当条件满足后，生成阶段结果

建议第一版做成有限步数：

- 最多 3 到 5 步
- 防止跑飞
- 便于调试和日志追踪

### 5. Final Reporter

最后不要只吐出一坨文本，而是结构化输出：

- Code Review
- 测试建议
- 单元测试建议
- 审查依据
- 使用过的工具
- 命中的知识来源

这样前端展示会很清晰，也更像真正的 Agent 系统。

## 推荐落地方式

不要推翻现有三阶段任务体系，应该在现有任务体系上做“内部升级”。

也就是：

- 前端任务页面基本不变
- 任务入口基本不变
- Webhook 触发逻辑基本不变
- 主要升级后端执行逻辑

### 当前结构

目前更像这样：

```text
Webhook -> 创建任务 -> 固定调用 Prompt A/B/C -> 保存结果
```

### 升级后结构

升级为：

```text
Webhook
-> 创建任务
-> PR Review Agent
   -> Planner
   -> Tools
   -> Review Step
   -> Testing Step
   -> Unit Test Step
   -> Final Report
-> 保存结果
```

这样前端几乎不需要大改，但你后端已经是 Agent 模式。

## 建议新增的文件

推荐新增这些文件：

### 后端服务层

- `backend/services/pr_review_agent_service.py`
  - Agent 主入口
  - 管理状态、执行循环、调度工具

- `backend/services/pr_review_tool_service.py`
  - 专门封装 PR 审查相关工具

### Prompt 层

- `backend/prompts/pr_review_agent_planner.py`
  - Planner Prompt

- `backend/prompts/pr_review_agent_executor.py`
  - 执行阶段的动作决策 Prompt

- `backend/prompts/pr_review_agent_reporter.py`
  - 最终汇总 Prompt

### Schema / State

- `backend/schemas/pr_review_agent.py`
  - Agent State
  - Planner 输出结构
  - Tool Call 结构

如果你想更轻量，也可以先不拆 schema 文件，先在 service 里用 dataclass。

## 与现有代码的关系

### 可以复用的部分

- `backend/services/agent_service.py`
  里面已有 PR 自动审查主流程，可逐步迁移

- GitHub 仓库和任务相关 service
  直接复用

- 现有 Prompt
  可以先复用已有 `github_pr_review.py` 和 `github_pr_testing.py`

- 知识库检索 service
  直接作为工具接入

### 建议保留的部分

- 当前任务表结构
- 当前任务详情接口
- 当前前端阶段展示

### 建议逐步替换的部分

- 把固定的“顺序生成三段内容”替换成：
  - 先规划
  - 再按步骤执行
  - 再汇总输出

## 第一版建议做成什么程度

为了控制复杂度，第一版不要做：

- 多 Agent 协作
- 自动反思很多轮
- 无限工具循环
- 自动修改代码
- 自动回评审评论到 GitHub

第一版只要做到：

1. 有明确 Planner
2. 有真实 Tool Use
3. 有 Agent State
4. 有有限步执行循环
5. 最后产出结构化审查结果

这就已经足够称为一个完整且严谨的 Agent 模块。

## 面试里怎么讲

推荐说法：

> 项目早期的 GitHub PR 自动审查是固定三阶段流水线，虽然能完成 Code Review、测试建议和单元测试建议，但对不同类型 PR 的适配性有限。  
> 后来我把这部分升级为 PR Review Agent：先由 Planner 判断 PR 类型和审查重点，再按需调用 GitHub、知识库和平台上下文工具补充信息，最后基于统一状态生成结构化审查结果。  
> 这样系统从固定工作流升级成了具备规划、工具调用和状态管理能力的单 Agent 审查模块。

这个表述比较真实，也和你现有项目强相关。

## 简历上怎么写

可以写成：

- 设计并实现 GitHub PR 审查 Agent，基于 Planner + Tool Use + State 的单 Agent 架构，支持按 PR 类型动态规划审查步骤并生成 Code Review、测试建议和单元测试建议；

或者更朴素一点：

- 将 GitHub PR 自动审查从固定流水线升级为 Agent 模式，引入规划、工具调用和状态管理机制，提升复杂 PR 审查的灵活性和上下文利用能力；

## 推荐实施顺序

建议按下面顺序落地：

1. 新增 Agent State 结构
2. 新增 Planner Prompt
3. 将 GitHub PR 信息封装成工具
4. 将知识库查询封装成工具
5. 实现有限步 Agent Loop
6. 复用现有三阶段输出结构接前端
7. 加日志，记录每一步的计划、工具、结果

## 最后建议

如果你的目标是：

- 真正做出一个完整 Agent 模块
- 又不想把项目整体推倒重来

那么最优解不是“把聊天随便包装成 Agent”，而是：

- 选取 `GitHub PR 自动审查` 这一条最适合的业务链路
- 用单 Agent + Planner + Tools + State 的方式完成升级

这样改动真实、展示清晰、面试也最有说服力。
