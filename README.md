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

