# 武大计算机学院校企合作 AI 研发协作平台

面向团队研发协作场景的 AI 平台，围绕团队知识库问答、RAG 检索、多轮会话记忆、AI Code Review、GitHub PR 自动审查、对话式 ChatAgent 等能力进行设计与实现，服务于团队研发过程中的知识复用、代码审查、测试补充和日常协作查询等场景。

项目已完成前后端一体化落地，部署在阿里云服务器。

## 项目简介

项目围绕两类研发痛点展开：

- 团队研发流程中，代码审查、测试补充、PR 跟进依赖人工，效率低、标准不统一
- 团队文档、项目经验和历史知识难以沉淀，知识复用和问答查询成本高

围绕上述问题，平台提供两条核心能力链路：

- 团队智能问答知识库：基于文档解析、语义分块、混合检索、短期记忆与长期记忆，支撑面向团队资料的 RAG 问答
- GitHub PR 自动审查：基于 Webhook 触发审查任务，自动生成 Code Review、测试建议和单元测试建议

在此基础上，聊天模块进一步实现了基于工具调用的 ChatAgent，可在对话中按需查询平台内数据、知识库内容以及 GitHub 相关协作信息。

## 项目亮点

- 设计并落地团队智能问答知识库，支持文档上传、向量化存储、混合检索与 RAG 问答
- 设计短期记忆机制，基于滑动窗口、摘要压缩与 Redis 存储，保障多轮对话上下文连贯
- 设计长期记忆机制，基于结构化提取、向量化存储与语义召回，支撑个性化问答体验
- 设计 GitHub PR 自动审查流程，支持私有仓库接入、Webhook 触发、PR 自动生成 Code Review、测试建议和单元测试建议
- 设计并维护多套 Prompt，包括 Code Review、测试建议、单元测试生成、查询改写、工具调用等提示词，提高输出质量与稳定性
- 实现对话式 ChatAgent，支持平台仓库、任务、文档、知识库等工具查询，并可结合知识库与通用能力完成回答
- 前端提供统一工作台，支持仓库接入、任务筛选、审查结果展示、对话切换、知识库管理与 Markdown 渲染

## 功能模块

### 1. 团队知识库问答

- 支持上传 `txt / pdf / docx` 文档
- 文档自动解析、切分、向量化并写入知识库
- 支持基于知识库内容的 RAG 问答
- 支持知识库命中片段与来源展示

### 2. 会话记忆系统

- 短期记忆：滑动窗口 + 摘要压缩 + Redis 缓存
- 长期记忆：结构化提取 + 向量化存储 + 语义召回
- 支持历史会话切换、重命名、删除和持续追问

### 3. ChatAgent

- 面向研发协作场景的对话式 Agent
- 支持按需调用平台内置工具
- 支持知识库查询、仓库查询、任务查询、文档查询等能力
- 支持在无知识库命中时退回通用回答

### 4. AI Code Review

- 支持输入代码或 Diff 进行审查
- 支持 Markdown 结果展示
- 支持输出逻辑问题、边界风险、可维护性建议与修复建议

### 5. GitHub PR 自动审查

- 支持私有仓库接入
- 支持 GitHub Webhook
- 支持 `opened / reopened / synchronize` 事件自动触发
- 自动生成三阶段审查结果：
  - Code Review
  - 测试建议
  - 单元测试建议 / 示例代码
- 支持任务状态流转、时间戳、失败提示与结果持久化

## 页面说明

### 登录页

- 用户注册 / 登录
- 登录后自动加载会话、知识库、仓库和任务数据

### 智能问答页

- 多轮对话
- 历史会话切换
- RAG 问答
- ChatAgent 工具查询
- 长期记忆展示

### 知识库页

- 文档上传
- 文档列表展示
- 文档状态查看
- 文档删除

### Code Review 页

- 输入代码 / Diff
- 流式输出审查结果
- Markdown 渲染展示

### GitHub Agent 页

- 仓库接入与使用说明
- 已接入仓库列表
- 任务队列与状态筛选
- 审查结果分阶段展示

### 设置页

- 模型配置
- API 地址配置
- LLM / Embedding 连通性测试

## 技术栈

### 后端

- FastAPI
- LangChain
- SQLAlchemy + SQLite
- Redis
- ChromaDB
- httpx
- OpenAI Compatible API

### 前端

- React
- TypeScript
- Vite
- Tailwind CSS
- React Markdown

### 部署

- Docker
- Docker Compose
- Shell 一键部署脚本

## 核心实现

### 1. RAG 检索链路

项目知识库问答链路包括：

1. 用户问题输入
2. 查询改写
3. 文档语义分块
4. 混合检索
5. 结果融合
6. 构建上下文 Prompt
7. 生成最终回答

当前实现采用：

- `TokenTextSplitter` 做文档分块
- Chroma 做向量存储与召回
- BM25 + 向量检索做混合检索
- 改写问题与原问题双路召回降低漏检索风险
- 检索结果相关性过滤，避免无关片段误命中

### 2. 会话记忆机制

短期记忆部分：

- 使用滑动窗口管理近轮对话
- 当上下文过长时自动摘要压缩
- 使用 Redis 持久化短期上下文

长期记忆部分：

- 从对话中提取结构化用户信息
- 通过向量化存储实现长期沉淀
- 在后续问答中基于语义相似度召回相关偏好和历史信息

### 3. ChatAgent

聊天模块实现了完整的 ChatAgent 调度逻辑，能够在问答过程中自主判断：

- 直接回答
- 查询知识库
- 查询平台内仓库 / 任务 / 文档数据
- 调用 GitHub 相关查询工具

Agent 当前支持的工具包括：

- 已接入仓库查询
- 最近任务查询
- 任务详情查询
- 文档列表查询
- 知识库搜索
- GitHub PR 查询
- GitHub PR 文件变更查询

说明：

- 平台内部状态查询采用内置工具实现
- GitHub 实时协作信息查询支持接入 GitHub MCP 能力，并保留现有 GitHub API 回退链路

### 4. GitHub PR 自动审查工作流

PR 自动审查流程如下：

1. 用户接入 GitHub 私有仓库
2. 配置 Webhook
3. PR 事件触发审查任务
4. 后端拉取 PR 信息与文件差异
5. 构建审查 Prompt
6. 分阶段执行审查
7. 前端展示任务状态与结果

当前审查范围基于 PR 全量 Diff，而不是仅最近一次提交。

### 5. Prompt 体系

项目将 Prompt 从业务代码中拆分为独立目录统一维护，当前包括：

- Code Review Prompt
- GitHub Agent Prompt
- 测试建议 Prompt
- 单元测试生成 Prompt
- RAG Prompt
- 记忆提取 Prompt
- 查询改写 Prompt
- Tool / Agent Prompt

## 项目结构

```text
AI/
├── backend/
│   ├── prompts/              # Prompt 独立目录
│   ├── routers/              # 路由层
│   ├── services/             # 业务逻辑层
│   ├── models/               # 数据模型
│   ├── schemas/              # 请求 / 响应结构
│   ├── utils/                # 工具方法
│   ├── config.py             # 配置项
│   └── .env.example
├── frontend/
│   ├── src/pages/            # 页面
│   ├── src/components/       # 组件
│   ├── src/api/              # 接口封装
│   └── src/store/            # 状态管理
├── deploy.sh                 # 一键部署
├── deploy_backend_only.sh    # 仅后端部署
├── setup_ssh_key.sh          # 免密 SSH 配置
└── docker-compose.yml
```

## 本地启动

### 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000 --workers 1
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`

## Docker 启动

```bash
cp backend/.env.example backend/.env
docker-compose up -d
```

## 推荐模型配置

当前可运行配置示例：

```bash
APP_SECRET_KEY=一段固定不变的随机密钥
OPENAI_API_KEY=你的智谱API Key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_USER_AGENT=agent/8.0
CHAT_MODEL=glm-4.7
EMBEDDING_MODEL=embedding-3
REQUEST_TIMEOUT=180
LLM_RETRY_ATTEMPTS=3
EMBEDDING_BATCH_SIZE=32
```

补充说明：

- `APP_SECRET_KEY` 用于登录态、GitHub Token 等本地加密
- 聊天与 Agent 回答走 `chat/completions`
- 向量检索和记忆走 `embeddings`

如需为 Embedding 单独配置兼容供应商，也支持：

```bash
EMBEDDING_API_KEY=你的兼容供应商Key
EMBEDDING_BASE_URL=https://你的兼容供应商地址/v1
EMBEDDING_MODEL=text-embedding-v3
```

## 一键部署

### 首次部署

```bash
chmod +x setup_ssh_key.sh deploy.sh
./setup_ssh_key.sh
```

### 正常部署

```bash
./deploy.sh
```

### 仅部署后端

```bash
chmod +x deploy_backend_only.sh
./deploy_backend_only.sh
```

### 临时覆盖服务器信息

```bash
SERVER_USER=root SERVER_HOST=101.133.137.152 SERVER_PATH=/root ./deploy.sh
```

## GitHub Webhook 配置

接入仓库后，前端会生成对应的 Webhook URL，在 GitHub 仓库中完成如下配置：

1. 进入 `Settings -> Webhooks`
2. 点击 `Add webhook`
3. 填入平台提供的 `Webhook URL`
4. 填入页面配置的 `webhook_secret`
5. Content type 选择 `application/json`
6. 事件选择 `Pull requests`

支持触发的事件：

- `opened`
- `reopened`
- `synchronize`

说明：

- 只有已打开 PR 的对应分支产生新提交时，才会触发 `synchronize`

## 当前已实现能力总结

- 用户注册 / 登录
- 团队知识库问答
- RAG 检索
- 多轮会话管理
- 短期记忆
- 长期记忆
- ChatAgent 工具调用
- 文档上传与知识库管理
- AI Code Review
- GitHub PR 自动审查
- 仓库接入与 Webhook 联动
- Docker 部署与服务器在线运行
