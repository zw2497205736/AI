# AI 研发协作平台

一个面向团队研发流程的 AI 协作平台，覆盖知识库问答、会话记忆、手动 Code Review、GitHub PR 自动审查、任务追踪与仓库管理。

这个项目的重点不是“做一个聊天页面”，而是把研发团队里最常见、最琐碎、最依赖人工经验的几条链路真正打通：

- 团队文档沉淀成可检索知识库
- 多轮问答能记住上下文和用户偏好
- 手动代码审查可以直接落地
- GitHub PR 可以通过 Webhook 自动触发三阶段审查

## 项目亮点

### 1. 不只是 RAG，而是完整的团队知识库链路

- 支持 `txt / md / pdf / docx` 文档上传
- PDF / DOCX 优先走 `MarkItDown` 解析，失败自动降级
- 检索链路采用 `BM25 + 向量检索`
- 支持查询改写、相关性筛选、来源卡片展示
- 支持多轮追问、长期记忆与个性化上下文补充

### 2. 文档分块做过多轮实战优化

这个项目里最难的一块不是“接个向量库”，而是把知识单元切对。

做过的关键优化包括：

- 从纯 token 分块升级为：
  - 结构优先分块
  - 语义感知二次切分
  - 小块合并
  - token 约束兜底
- 针对“切得太碎导致回答只剩概述”的问题，继续补了：
  - 邻接 chunk 补全
  - 检索深度提升
  - 相关性筛选回退

目标是让系统尽量召回“完整知识单元”，而不是只召回标题和摘要。

### 3. 做了真实可用的 ChatAgent，而不是纯问答 Prompt

聊天模块不是简单的“问题 + 知识库 = 回答”，而是一个轻量 Agent：

- 可以判断是直接回答还是调用工具
- 能查询仓库、任务、文档、知识库
- 支持 RAG 问答与平台内部数据查询结合
- 模型空正文时有显式 fallback，不会把推理链直接暴露给前端

### 4. GitHub PR 自动审查已经升级成单 Agent 架构

支持：

- 私有仓库接入
- GitHub Webhook 自动触发
- PR 三阶段输出：
  1. Code Review
  2. 测试建议
  3. 单元测试建议 / 示例骨架

PR Agent 当前不是简单串 Prompt，而是拆成：

- Planner
- Executor
- Replanner
- Reporter

前端还支持展示：

- 任务状态
- 三阶段输出
- Agent 执行轨迹
- 工具调用记录
- 重规划记录
- 知识来源

### 5. 解决过一堆真正的工程问题，而不是只停留在功能演示

这个项目里处理过的实际问题包括：

- embedding 模型切换后的维度冲突
- 知识库切块过碎导致回答质量下降
- 模型只返回 `reasoning_content` 不返回最终正文
- 流式输出链路在模型、后端、Nginx、前端多层之间的不稳定
- PR Agent 控制层 JSON 输出不稳定
- 服务器环境变量被部署覆盖
- 运行时数据与代码目录混在一起导致反复污染
- 老版 `docker-compose` 重建容器时的 `ContainerConfig` 异常

也正因为这些问题都踩过、修过，所以这不是一个“只会跑 demo”的项目，而是一个做过稳定性治理的项目。

## 功能概览

### 团队知识库问答

- 文档上传、解析、分块、向量化
- 知识库问答
- 来源展示
- 持续追问

### 多轮会话与记忆

- 短期记忆：滑动窗口 + 摘要压缩 + Redis
- 长期记忆：结构化提取 + 向量化存储 + 语义召回
- 会话切换、重命名、删除

### 手动 Code Review

- 输入代码或 Diff
- 生成 Markdown 格式审查结果
- 输出风险点、边界条件、改进建议

### GitHub PR 自动审查

- 接入 GitHub 仓库
- Webhook 自动触发
- 三阶段审查输出
- 任务状态流转
- Agent Trace 展示

## 项目难点

这个项目真正难的地方不在“页面多”，而在下面几条链路的工程稳定性：

### 1. RAG 质量不是靠接个向量库就能解决

真正难点在于：

- 文档解析质量
- 分块是否保留完整语义单元
- 检索是否能拿到真正有用的 chunk
- 生成时如何避免“命中了资料但回答仍然很空”

### 2. Agent 最难的不是会不会“思考”，而是稳不稳定

PR Agent 这条链路里，模型既要：

- 理解 diff
- 决定下一步动作
- 严格输出 JSON
- 生成可读 Markdown

这类系统最容易死在“格式不稳定”上，所以项目里专门做了：

- 控制层 / 生成层模型拆分
- JSON 失败兜底
- 阶段缺失补生成
- 执行轨迹可视化

### 3. 真正上线后，部署和数据治理比功能本身更容易出坑

项目后期重点做了三件事：

- 配置与代码分离
- 运行时数据与代码分离
- 部署脚本避免覆盖服务器 `.env` 和运行数据

这部分是项目从“能跑”走向“能维护”的关键。

## 技术栈

### 后端

- FastAPI
- SQLAlchemy + SQLite
- Redis
- ChromaDB
- LangChain Chroma / Text Splitters
- OpenAI Compatible API
- MarkItDown

### 前端

- React
- TypeScript
- Vite
- Tailwind CSS
- Zustand
- React Markdown

### 部署

- Docker
- Docker Compose
- Shell 一键部署脚本

## 当前架构重点

### 知识库链路

`文档上传 -> 文档解析 -> 结构化分块 -> 向量化 -> 混合检索 -> 相关性筛选 -> 构建上下文 -> 最终回答`

### PR 审查链路

`GitHub Webhook -> 创建任务 -> 拉取 PR 信息与 diff -> Planner -> Executor -> 知识检索 -> 三阶段生成 -> Reporter -> 前端展示`

## 项目结构

```text
AI/
├── backend/
│   ├── models/
│   ├── prompts/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   ├── config.py
│   └── .env.example
├── frontend/
│   ├── src/api/
│   ├── src/components/
│   ├── src/pages/
│   ├── src/store/
│   └── src/types/
├── docker-compose.yml
├── deploy.sh
├── deploy_backend_only.sh
└── DEPLOYMENT.md
```

## 本地启动

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000 --workers 1
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 部署

### 只部署 backend

```bash
./deploy_backend_only.sh
```

### 部署前后端

```bash
./deploy.sh
```

## 运维原则

当前项目已经明确分层：

- 本机改代码
- 服务器改 `.env`
- 运行时数据放 Docker Volume
- 部署包不覆盖服务器配置和运行数据

详细运维说明见：

- [DEPLOYMENT.md](/Users/zhaowei/Documents/就业/AI项目/AI/DEPLOYMENT.md)

## 当前经验结论

这个项目做到现在，最大的经验不是“某个模型最强”，而是：

- 生产主链路优先稳定，不优先追求最强模型
- RAG 质量高度依赖解析、分块、检索策略
- Agent 成败取决于状态机、兜底和可观测性，不取决于“会不会思考”
- 配置、代码、数据如果不分离，后面一定反复踩坑

如果你想快速理解这个项目，建议优先看：

1. `README.md`
2. `DEPLOYMENT.md`
3. `backend/services/rag_service.py`
4. `backend/services/chat_agent_service.py`
5. `backend/services/pr_review_agent_service.py`
6. `backend/prompts/README.md`
