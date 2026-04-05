# AI Team Assistant

## 本地启动

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
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

## Docker 启动

```bash
cp backend/.env.example backend/.env
docker-compose up -d
```

## 智谱官方推荐配置

`backend/.env` 建议至少配置为：

```bash
APP_SECRET_KEY=一段固定不变的随机密钥
OPENAI_API_KEY=你的智谱API Key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
CHAT_MODEL=glm-4.7-flash
EMBEDDING_MODEL=embedding-3
REQUEST_TIMEOUT=180
LLM_RETRY_ATTEMPTS=3
```

说明：

- `APP_SECRET_KEY` 用于登录态、GitHub Token 等本地加密，后续不要随便改
- 聊天与 GitHub Agent 现在走 `chat/completions`
- 向量/记忆走 `embeddings`
- 这套配置比之前第三方 OpenAI 代理更适合演示和稳定运行

如果你想让 embedding 单独走另一个兼容供应商，可以额外配置：

```bash
EMBEDDING_API_KEY=你的旧供应商Key
EMBEDDING_BASE_URL=https://你的旧供应商地址/v1
EMBEDDING_MODEL=text-embedding-v3
```

留空时会默认复用聊天的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。

## 一键部署到服务器

首次先配置免密 SSH：

```bash
chmod +x setup_ssh_key.sh deploy.sh
./setup_ssh_key.sh
```

之后每次部署只需要：

```bash
./deploy.sh
```

如果只改了后端，想更快一点：

```bash
chmod +x deploy_backend_only.sh
./deploy_backend_only.sh
```

如果服务器地址以后变了，可以临时覆盖：

```bash
SERVER_USER=root SERVER_HOST=101.133.137.152 SERVER_PATH=/root ./deploy.sh
```
