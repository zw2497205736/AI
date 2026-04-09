---
name: prompt-designer
description: 当需要新增、修改、评审本项目中的提示词时使用，适用于 backend/prompts 下的 Code Review、测试建议、单元测试建议、查询改写、RAG、Tool/Agent 提示词。该 skill 解决本项目提示词长期维护中的核心痛点：提示词风格漂移、结构不统一、输出不稳定、提示词与代码能力不一致。
---

# Prompt Designer

这个 skill 只服务一个明确目标：

- **把本项目中的提示词设计成稳定、统一、可维护的生产资产**

不要把它用于普通代码修改、部署问题、前端样式调整或 README 编写。

## 适用场景

只有在下面这些场景才使用：

1. 新增 `backend/prompts/` 下的提示词
2. 修改已有提示词
3. 审查某个提示词是否写乱了
4. 统一多套 Prompt 的结构和风格

## 本项目里的真实痛点

本项目的 Prompt 已经覆盖了多个核心模块：

- Code Review Prompt
- 测试建议 Prompt
- 单元测试建议 Prompt
- 查询改写 Prompt
- RAG Prompt
- Tool / Agent Prompt

这些 Prompt 在长期迭代里最容易出现 4 个问题：

1. **换模型后输出风格变飘**
2. **同类 Prompt 多次修改后，写法越来越不一致**
3. **提示词约束不够，输出结构越来越乱**
4. **提示词写得太强，但代码实际并不支持**

这个 skill 的任务就是围绕这些问题做治理。

## 管理范围

只处理这些文件：

- `backend/prompts/manual_code_review.py`
- `backend/prompts/github_pr_review.py`
- `backend/prompts/github_pr_testing.py`
- `backend/prompts/rag_query_rewrite.py`
- `backend/prompts/rag_answer.py`
- `backend/prompts/chat_agent_tool.py`

未来如果新增 Prompt，也默认放进 `backend/prompts/` 下统一管理。

## 设计目标

每次改 Prompt，都要尽量满足这 4 个目标：

1. **结构统一**
2. **风格稳定**
3. **输出可控**
4. **能力和代码一致**

## 统一结构模板

本项目中的 Prompt，默认优先采用下面这套结构：

1. `Role`
2. `Task`
3. `Constraints`

只有确实有必要时，才额外补：

4. `Input`
5. `Output Requirements`

不要同一个项目里每个 Prompt 都换一套写法。

## 设计规则

### 1. 先看调用方，再改 Prompt

改 Prompt 前，必须先看是谁在调用：

- 对应的 `router`
- 对应的 `service`
- 输入内容是什么
- 输出格式要求是什么

如果没看清调用链，不要直接改 Prompt。

### 2. Prompt 不能超过代码真实能力

不要写这种会让模型“看起来很强、实际上做不到”的句子：

- “请自行联网查询”
- “请读取仓库所有文件”
- “请直接判断平台实时状态”
- “请自由决定调用任意外部能力”

Prompt 只能描述当前代码链路真实支持的能力。

### 3. 约束要具体，不能写空话

优先使用这种写法：

- `只输出问题本身，不要解释`
- `如果资料不足，明确说明资料不足`
- `按问题、风险、建议结构输出`
- `只基于提供内容回答，不要扩写`

不要使用这种空泛写法：

- `尽量回答得更好`
- `适当补充`
- `自由发挥`
- `尽量全面`

### 4. 输出要考虑前端展示

本项目多个页面直接渲染 Markdown，所以 Prompt 输出默认应该：

- 结构清楚
- 标题简短
- 列表可读
- 不乱输出 JSON

只有在后端明确按 JSON 解析时，才允许设计 JSON 输出。

### 5. 同类 Prompt 的风格要统一

同一类任务，不要今天一个写法、明天一个写法。

例如：

- Code Review Prompt 要统一关注：逻辑、边界、风险、测试
- 测试建议 Prompt 要统一关注：主路径、边界、异常、回归点
- Tool / Agent Prompt 要统一关注：工具名、参数、动作边界

## 分类型设计要求

### Code Review Prompt

重点约束：

- 优先找真实问题，不要只挑格式
- 优先关注逻辑缺陷、边界问题、回归风险、缺失测试
- 输出要方便前端 Markdown 展示

### 测试建议 Prompt

重点约束：

- 输出要具体到测试点，而不是泛泛地说“补边界测试”
- 优先覆盖主路径、空值、异常值、非法输入和回归点

### 单元测试建议 Prompt

重点约束：

- 输出要尽量接近可落地的测试样例
- 不要只给概念，不给结构

### Query Rewrite Prompt

重点约束：

- 不改变原问题意图
- 保留关键技术词、模块名、项目名
- 只补全上下文，不扩大问题范围

### RAG Prompt

重点约束：

- 命中知识库时，回答必须贴近资料
- 未命中时，不能假装引用知识库
- 如果系统支持通用回答回退，Prompt 必须允许这种回退

### Tool / Agent Prompt

重点约束：

- 工具名必须和代码里的注册工具一致
- 参数必须和代码里实际支持的一致
- 不要描述代码里不存在的工具能力

## 自动检查清单

每次修改 Prompt 后，至少检查这几件事：

1. 有没有 `Role / Task / Constraints`
2. 输出格式是否明确
3. 是否存在超出代码能力的描述
4. 是否和同类 Prompt 风格保持一致
5. 是否比原来更稳定，而不是更花哨

只要有一项不满足，就继续改。

## 最终标准

这个 skill 的好坏，不看 Prompt 写得多华丽，只看三件事：

1. 输出有没有更稳定
2. 多套 Prompt 有没有更统一
3. Prompt 和代码能力有没有更贴合

如果答案是肯定的，这个 Prompt 修改才算合格。
