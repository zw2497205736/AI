# Prompt 目录说明

该目录集中管理项目里的核心提示词，按业务链路拆分，目标是做到两点：

- 文件名一眼能看出服务于哪个场景
- 面试、维护、改 Prompt 时能快速定位

## 文件映射

| 文件 | 对应模块 | 对应功能入口 | 用途 |
| --- | --- | --- | --- |
| `github_pr_review.py` | `backend/services/agent_service.py` | GitHub Agent / PR 自动审查 | 生成 Code Review 和测试建议 |
| `github_pr_testing.py` | `backend/services/agent_service.py` | GitHub Agent / PR 自动审查 | 生成单元测试建议与测试覆盖分析 |
| `manual_code_review.py` | `backend/services/code_review_service.py` | 手动 Code Review 页面 | 对用户粘贴的代码做人工触发审查 |
| `rag_answer.py` | `backend/services/rag_service.py` | 智能问答 / 知识库问答 | 组织知识库问答主回答 |
| `rag_query_rewrite.py` | `backend/utils/query_rewriter.py` | 智能问答 / RAG 检索前处理 | 对用户问题做查询改写 |
| `chat_memory.py` | `backend/services/memory_service.py` | 多轮对话记忆 | 生成会话摘要、提取长期记忆 |
| `chat_agent_tool.py` | `backend/services/chat_tool_service.py` | ChatAgent | 负责工具选择、动作规划、工具结果整理 |

## 为什么这样命名

这次命名调整的核心不是“更学术”，而是“更少歧义”。

- `agent.py` 改为 `github_pr_review.py`
  以前看不出这是 GitHub PR 审查 Prompt，容易和聊天 Agent 混淆

- `testing.py` 改为 `github_pr_testing.py`
  以前看不出它服务的是 GitHub PR 自动审查链路

- `code_review.py` 改为 `manual_code_review.py`
  明确它对应的是手动代码审查，不是 PR 自动审查

- `query.py` 改为 `rag_query_rewrite.py`
  明确这是 RAG 查询改写，不是任意查询处理

- `rag.py` 改为 `rag_answer.py`
  明确它负责最终回答组织

- `memory.py` 改为 `chat_memory.py`
  明确它是聊天记忆相关 Prompt

- `tool.py` 改为 `chat_agent_tool.py`
  明确它服务于聊天 Agent 的工具调用

## 目录理解方式

如果你想快速理解这个目录，不要按“文件夹”理解，直接按业务链路理解：

1. GitHub PR 自动审查
2. 手动代码审查
3. RAG 知识库问答
4. 会话记忆
5. ChatAgent 工具调用

这样看，`prompts` 目录本质上就是“业务能力对应的提示词层”。

## Prompt 编写约束

项目里的 Prompt 尽量统一包含以下要素：

1. `Role`
   明确模型扮演的角色

2. `Task`
   明确本轮要完成的任务

3. `Constraints`
   明确边界、禁止事项和优先级

4. `Output Format`
   明确输出结构，便于前端展示和后处理

## 维护建议

- 改 Prompt 时，优先改对应业务文件，不要把多个场景混写进一个文件
- GitHub PR 自动审查和手动 Code Review 要分开维护，避免角色漂移
- RAG 回答 Prompt 和查询改写 Prompt 要分开迭代，便于定位检索问题还是生成问题
- ChatAgent 的工具选择 Prompt 不要和最终回答 Prompt 混在一起，避免后续工具扩展时失控
