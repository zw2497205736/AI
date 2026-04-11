# 运维说明

## 1. 总原则

后续项目运维统一遵循以下原则：

- 本机负责修改代码与部署脚本
- 服务器负责运行、验证与排障
- 配置与代码分离
- 运行时数据与代码分离
- 部署时不再打包运行时数据

## 2. 三类内容的边界

### 2.1 代码

这类内容跟随 Git 和部署脚本发布：

- `backend/*.py`
- `frontend/src/*`
- `docker-compose.yml`
- `Dockerfile`
- `requirements.txt`
- `deploy.sh`
- `deploy_backend_only.sh`

### 2.2 配置

这类内容不应被部署包覆盖：

- `backend/.env`
- 模型供应商与模型名
- API Key
- Base URL
- Redis 地址
- 数据库路径
- Chroma 路径

当前策略：

- 服务器上的 `backend/.env` 独立维护
- 部署脚本自动保留已有 `backend/.env`

### 2.3 运行时数据

这类内容绝不能跟代码一起打包部署：

- SQLite 数据库
- Chroma 向量库
- Redis 数据
- 用户信息
- 聊天记录
- GitHub 仓库配置
- GitHub 任务记录
- 知识库文档索引

## 3. 当前 backend 真实运行数据位置

当前 `docker-compose.yml` 中 backend 使用的是：

- `DATABASE_URL=sqlite+aiosqlite:///./data/app.db`
- `CHROMA_PERSIST_DIR=./data/chroma_db`

同时挂载了 Docker volume：

- `backend_data:/app/data`

在当前项目下，真实卷名通常是：

- `ai_backend_data`

因此 backend 真实运行数据在容器中是：

- `/app/data/app.db`
- `/app/data/chroma_db`

## 4. 为什么以前会反复出问题

之前之所以出现这些问题：

- 切回智普后又变回 kaimarket
- embedding 改了又变回旧模型
- 清了向量库但维度冲突还在

根本原因是两个：

1. 服务器配置曾经手改，但本机未同步
2. 本机项目目录中带着旧 `.env`、旧 `app.db`、旧 `chroma_db`，部署脚本整包上传后把服务器覆盖回旧状态

## 5. 当前部署脚本的变化

现在 `deploy.sh` 和 `deploy_backend_only.sh` 会在打包时自动排除：

- `.git`
- `venv`
- `backend/.env`
- `backend/app.db`
- `backend/chroma_db`
- `backend/__pycache__`
- `frontend/node_modules`
- `frontend/dist`
- `.DS_Store`
- `._*`

同时在服务器部署前会先备份旧的：

- `backend/.env`

解压后再恢复，防止配置被部署包覆盖。

## 6. 常用部署方式

### 6.1 只部署 backend

适用于：

- 后端逻辑修改
- Prompt 修改
- Agent 逻辑修改
- 日志与服务层修改

命令：

```bash
cd /Users/zhaowei/Documents/就业/AI项目/AI
./deploy_backend_only.sh
```

### 6.2 部署前后端

适用于：

- 前端页面改动
- API 结构调整
- 页面布局和展示改动

命令：

```bash
cd /Users/zhaowei/Documents/就业/AI项目/AI
./deploy.sh
```

## 7. 正确的配置变更流程

### 7.1 推荐原则

配置变更不要再走“先在服务器硬改，再部署”的方式。

正确流程：

1. 本机记录清楚要变更的配置
2. 服务器修改 `backend/.env`
3. 重启 backend
4. 验证容器内真实配置

### 7.2 验证容器内实际生效值

```bash
cd /root/AI
docker exec -it ai_backend_1 sh -c 'python - <<'"'"'PY'"'"'
from config import settings
print("OPENAI_BASE_URL =", settings.openai_base_url)
print("CHAT_MODEL =", settings.chat_model)
print("EMBEDDING_MODEL =", settings.embedding_model)
PY'
```

### 7.3 模型配置联通测试

```bash
curl -s http://localhost:8000/api/settings/test
```

期望结果：

```json
{"message":"Connection ok","chat_ok":true,"embedding_ok":true}
```

## 8. 正确的数据处理流程

### 8.1 只重建知识库

适用于：

- 更换 embedding 模型
- 向量维度冲突
- 知识库索引污染

这类问题理论上只需要重建：

- Chroma 向量库
- `documents` 相关记录

不应该影响：

- 用户信息
- 聊天记录
- GitHub 仓库
- PR 任务

### 8.2 全新初始化 backend 数据

适用于：

- 环境已经混乱，无法确认当前数据来源
- 旧数据库、旧向量库、旧配置互相污染
- 需要回到绝对干净状态

先备份 volume：

```bash
cd /root/AI
mkdir -p /root/AI/backups
docker run --rm -v ai_backend_data:/from -v /root/AI/backups:/to alpine sh -c "cd /from && tar -czf /to/backend_data_backup_$(date +%Y%m%d_%H%M%S).tar.gz ."
ls -lh /root/AI/backups
```

再清空 volume：

```bash
cd /root/AI
docker-compose down
docker volume rm ai_backend_data
docker-compose up -d --build backend
```

注意：

- 这会同时清掉数据库与向量库
- 后续需要重新注册 / 登录
- 需要重新接 GitHub 仓库
- 需要重新上传知识库文档

## 9. 常用验证命令

### 9.1 看容器状态

```bash
cd /root/AI
docker-compose ps
```

### 9.2 看 backend 日志

最近日志：

```bash
cd /root/AI
docker-compose logs --tail=100 backend
```

实时日志：

```bash
cd /root/AI
docker-compose logs -f backend
```

### 9.3 文档上传排障

文档上传接口即使返回 `200 OK`，后续 embedding/向量写入也可能失败。

当前 backend 已增加日志：

- `Document upload started`
- `Document upload finished`
- `Document upload failed`

如果前端文档状态显示 `error`，请优先看 backend 实时日志。

## 10. 常见问题与处理

### 10.1 为什么切换 embedding 模型后会报维度冲突

典型报错：

```text
Embedding dimension 2048 does not match collection dimensionality 8
```

原因：

- 旧向量库由旧 embedding 模型生成
- 新 embedding 模型维度不同
- 同一个 Chroma collection 不能混写不同维度

处理：

- 重建知识库向量库

### 10.2 为什么前端显示文档 error，但日志里只有 200

原因：

- 上传接口接收成功
- 后续解析、分块、embedding 或写入向量库失败
- 文档状态被写成 `error`

当前已经补充日志，可直接从 backend 日志看异常栈。

### 10.3 为什么部署后配置又“变回去了”

常见原因：

- 本机旧 `.env` 随部署包上传
- 服务器手改配置后，本机未同步

当前脚本已经默认排除 `backend/.env` 并保留服务器现有配置。

## 11. 推荐操作习惯

- 改代码：本机改，部署脚本发，服务器验证
- 改配置：服务器改 `.env`，重启 backend，验证容器配置
- 改数据：先备份，再重建或迁移
- 排障：先看日志，再看容器内真实配置，再看 volume 与数据路径

## 12. 当前项目最重要的结论

以后不要再把这些内容当代码一起部署：

- `backend/.env`
- `backend/app.db`
- `backend/chroma_db`

服务器不是主编辑环境。

本机负责代码，服务器负责运行，配置和运行数据独立维护。
