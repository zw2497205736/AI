# 武大计算机学院校企合作 AI 研发协作平台

面向团队研发协作场景的 AI 平台，围绕智能问答知识库、RAG 检索、多轮会话记忆、AI Code Review、GitHub PR 自动审查等能力进行设计与实现，目标是解决团队研发过程中代码评审效率低、测试补充成本高、知识沉淀和复用不足等问题。

该项目目前已经落地为可运行的前后端系统，支持本地启动、Docker 部署和服务器一键发布，可用于项目演示、课程展示和简历项目说明。

## 项目亮点

- 集成 GitHub PR 自动审查流程，支持在 `opened / reopened / synchronize` 事件触发后自动生成 Code Review、测试建议和单元测试建议。
- 设计并实现 AI 研发协作工作流，将 Prompt、问答知识库、代码审查、测试建议等能力统一到一个平台中。
- 构建团队智能问答知识库，支持文档上传、向量化检索、RAG 问答、多轮对话管理。
- 设计短期记忆机制，基于滑动窗口、摘要压缩和 Redis 存储提升长对话上下文连贯性。
- 设计长期记忆机制，支持结构化信息提取、向量化存储和语义召回，增强个性化问答体验。
- 针对 PR 审查场景设计多套 Prompt，包括 Code Review、测试建议、单元测试生成等，提升输出质量和稳定性。
- 前端提供完整任务看板，支持仓库接入、任务筛选、状态流转查看、Markdown 渲染展示。

## 功能模块

### 1. 智能问答知识库

- 支持上传 `txt / pdf / docx` 文档
- 文档自动切分、向量化并写入知识库
- 支持基于知识库内容进行 RAG 问答
- 支持会话标题、历史会话、长期记忆展示与管理

### 2. 短期 / 长期记忆

- 短期记忆：滑动窗口 + 对话摘要 + Redis 缓存
- 长期记忆：结构化信息提取 + 向量化存储 + 相似度召回
- 同时兼顾上下文连贯性和个性化问答体验

### 3. AI Code Review

- 支持输入代码或 Diff 进行审查
- 支持 Markdown 结果展示
- 支持基于提示词规则输出问题、风险和修改建议

### 4. GitHub PR 自动审查 Agent 场景

- 支持私有仓库接入
- 支持 GitHub Webhook
- 支持在 PR 事件触发后自动执行三阶段任务：
  - Code Review
  - 测试建议
  - 单元测试建议 / 示例代码
- 支持任务状态流转、失败提示、结果持久化和前端看板展示

说明：  
该模块属于场景化 Agent 工作流，具备自动触发、拉取上下文、分阶段执行和结果回写能力，但不是通用型自主智能体。

## 页面说明

### 登录页

- 用户注册 / 登录
- 进入平台后加载个人会话、记忆和任务数据

### 智能问答页

- 支持多轮对话
- 支持历史会话切换、重命名、删除
- 支持长期记忆展示

### 知识库页

- 支持文档上传、文档列表展示、删除
- 支持查看处理状态和错误信息

### Code Review 页

- 输入代码 / Diff 后进行流式审查
- 结果以 Markdown 渲染展示

### GitHub Agent 页

- 仓库接入与 Webhook 配置说明
- 已接入仓库列表
- 任务队列、状态筛选、时间戳展示
- AI 审查结果分面板查看

### 设置页

- 支持配置聊天模型、Embedding 模型和 API 接口地址
- 支持测试 LLM / Embedding 连通性

## 技术栈

### 后端

- FastAPI
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

## 核心实现说明

### Prompt 独立维护

项目中将 Prompt 从业务代码中拆分为独立目录统一管理，方便后续维护和迭代。当前已拆分的 Prompt 包括：

- Code Review Prompt
- GitHub Agent Prompt
- 测试建议 Prompt
- 单元测试生成 Prompt
- RAG Prompt
- 记忆提取 Prompt
- 查询重写 Prompt

### RAG 检索流程

项目中的问答检索链路包括：

1. 用户问题输入
2. 查询重写
3. 文档语义分块
4. 混合检索：
   - BM25 检索
   - 向量检索
5. 结果融合
6. 构建上下文 Prompt
7. 大模型生成回答

### GitHub PR 自动审查流程

项目中的 PR 自动审查流程如下：

1. 用户接入 GitHub 私有仓库
2. 配置 GitHub Webhook
3. PR 事件触发 Webhook
4. 后端拉取 PR 信息与 PR 文件差异
5. 构建审查 Prompt
6. 按阶段执行：
   - Code Review
   - 测试建议
   - 单元测试建议
7. 前端展示任务状态和结果

说明：  
当前审查范围基于 PR 全量 Diff，而不是仅最近一次提交。

## 本地启动

### 1. 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000 --workers 1
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:3000
```

后端默认地址：

```text
http://localhost:8000
```

## Docker 启动

```bash
cp backend/.env.example backend/.env
docker-compose up -d
```

## 推荐模型配置

当前项目已验证可运行的推荐配置为智谱官方接口：

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

说明：

- `APP_SECRET_KEY` 用于登录态、GitHub Token 等本地加密，部署后应固定，不建议频繁修改。
- 聊天与 GitHub Agent 走 `chat/completions`。
- 向量检索和记忆走 `embeddings`。

如需让 Embedding 单独走其他兼容供应商，也支持额外配置：

```bash
EMBEDDING_API_KEY=你的兼容供应商Key
EMBEDDING_BASE_URL=https://你的兼容供应商地址/v1
EMBEDDING_MODEL=text-embedding-v3
```

留空时默认复用聊天模型的配置。

## 一键部署到服务器

### 首次部署

先配置免密 SSH：

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

## GitHub Webhook 配置说明

接入仓库后，前端会生成对应的 Webhook URL。  
在 GitHub 仓库中完成如下配置：

1. 进入 `Settings -> Webhooks`
2. 点击 `Add webhook`
3. 填入平台提供的 `Webhook URL`
4. 填入你在页面配置的 `webhook_secret`
5. Content type 选择 `application/json`
6. 事件选择 `Pull requests`

支持触发的事件：

- `opened`
- `reopened`
- `synchronize`

说明：  
只有“已打开的 PR”在对应分支产生新提交时，才会触发 `synchronize`。

## 当前已实现能力总结

- 用户注册 / 登录
- 智能问答
- 多轮会话管理
- 短期记忆
- 长期记忆
- 文档上传与知识库问答
- AI Code Review
- GitHub 私有仓库接入
- GitHub PR 自动审查
- Prompt 独立维护
- Docker 容器化部署
- 一键部署脚本

## 后续可继续扩展的方向

- PR 增量 Diff 与全量 Diff 双模式切换
- 任务队列筛选、检索和统计面板进一步增强
- 审查结果导出
- 多模型切换与供应商配置面板增强
- 评论回写 GitHub PR
- 更细粒度的 Agent 工作流编排

## 说明

本项目用于校企合作场景下的 AI 研发协作能力实践与演示。  
README 中展示的功能、模块和流程均与当前项目实现内容保持一致，可直接作为项目展示和简历链接说明材料使用。
