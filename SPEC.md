# AI Team Assistant Platform — 项目实现规范

> 本文档由 Codex 执行，请严格按照以下规范实现完整的前后端项目。

---

## 一、项目概述

**项目名称**：AI Team Assistant（团队 AI 助理平台）

**核心功能**：
1. **智能问答知识库**（RAG 系统）：上传团队文档，AI 基于文档回答问题，支持混合检索（BM25 + 向量）、短期记忆（滑动窗口 + 摘要压缩）、长期记忆（用户偏好持久化）、流式输出。
2. **AI Code Review**：上传 diff 文件或粘贴代码变更，AI 生成结构化审查报告（Critical / Warning / Info 三级分类）。

**目标用户**：开发团队，用于提升开发效率和代码质量。

---

## 二、技术选型（最快开发速度优先）

| 层次 | 技术 | 说明 |
|------|------|------|
| 后端框架 | **Python FastAPI** | 异步、流式支持好、AI生态最完整 |
| LLM 接入 | **OpenAI Python SDK**（兼容 DashScope/本地） | 统一接口，支持多模型切换 |
| 向量数据库 | **ChromaDB**（本地文件存储） | 无需外部服务，开箱即用 |
| 传统数据库 | **SQLite + SQLAlchemy** | 轻量，无需安装 |
| 文档解析 | **PyPDF2 / python-docx / markdown** | 解析 PDF/Word/MD |
| BM25 检索 | **rank_bm25** | 纯 Python，轻量 |
| 前端框架 | **React 18 + Vite + TypeScript** | 最快的现代前端开发 |
| UI 组件库 | **Tailwind CSS + shadcn/ui** | 美观，开发迅速 |
| 状态管理 | **Zustand** | 轻量简洁 |
| HTTP 客户端 | **Axios + EventSource（SSE）** | 支持流式响应 |

---

## 三、项目目录结构

```
ai-team-assistant/
├── backend/
│   ├── main.py                    # FastAPI 入口
│   ├── requirements.txt
│   ├── .env.example               # 环境变量示例
│   ├── config.py                  # 全局配置
│   ├── database.py                # SQLAlchemy 数据库初始化
│   ├── models/
│   │   ├── __init__.py
│   │   ├── document.py            # 文档 ORM 模型
│   │   ├── memory.py              # 长期记忆 ORM 模型
│   │   └── conversation.py        # 会话 ORM 模型
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── document.py            # Pydantic schemas
│   │   ├── chat.py
│   │   └── code_review.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_service.py    # 文档上传、分块、入库
│   │   ├── rag_service.py         # RAG 检索、混合检索、Prompt 构建
│   │   ├── memory_service.py      # 短期记忆 + 长期记忆管理
│   │   ├── llm_service.py         # LLM 调用、流式输出、摘要生成
│   │   ├── code_review_service.py # AI Code Review 逻辑
│   │   └── embedding_service.py   # 向量化 + ChromaDB 管理
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── text_splitter.py       # 语义分块（固定Token + 语义相似度合并）
│   │   ├── bm25_retriever.py      # BM25 关键词检索
│   │   └── query_rewriter.py      # Query Rewriting
│   └── routers/
│       ├── __init__.py
│       ├── document_router.py     # /api/documents
│       ├── chat_router.py         # /api/chat (SSE 流式)
│       └── code_review_router.py  # /api/code-review
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css              # Tailwind 入口 + 全局样式
│       ├── types/
│       │   └── index.ts           # 全局 TypeScript 类型定义
│       ├── store/
│       │   ├── chatStore.ts       # 聊天状态（Zustand）
│       │   └── settingsStore.ts   # 设置状态
│       ├── api/
│       │   ├── axios.ts           # Axios 实例 + 拦截器
│       │   ├── documentApi.ts
│       │   ├── chatApi.ts
│       │   └── codeReviewApi.ts
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx    # 左侧导航
│       │   │   └── Layout.tsx     # 整体布局
│       │   ├── chat/
│       │   │   ├── ChatWindow.tsx # 聊天主界面
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── InputBar.tsx
│       │   │   └── MemoryPanel.tsx # 长期记忆展示面板
│       │   ├── documents/
│       │   │   ├── DocumentList.tsx
│       │   │   └── UploadDialog.tsx
│       │   ├── code-review/
│       │   │   ├── ReviewForm.tsx
│       │   │   └── ReviewReport.tsx
│       │   └── ui/                # 通用 UI 组件（shadcn/ui 风格）
│       │       ├── Button.tsx
│       │       ├── Badge.tsx
│       │       ├── Card.tsx
│       │       └── Spinner.tsx
│       └── pages/
│           ├── ChatPage.tsx       # 智能问答页面
│           ├── DocumentsPage.tsx  # 知识库管理页面
│           ├── CodeReviewPage.tsx # AI Code Review 页面
│           └── SettingsPage.tsx   # 设置页面（API Key 等）
│
├── docker-compose.yml             # 一键启动
└── README.md
```

---

## 四、后端实现规范

### 4.1 依赖（requirements.txt）

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-dotenv==1.0.1
sqlalchemy==2.0.30
aiosqlite==0.20.0
openai==1.30.1
chromadb==0.5.0
rank_bm25==0.2.2
PyPDF2==3.0.1
python-docx==1.1.2
markdown==3.6
tiktoken==0.7.0
python-multipart==0.0.9
pydantic==2.7.1
pydantic-settings==2.2.1
httpx==0.27.0
```

### 4.2 配置（config.py）

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    
    # RAG 参数
    chunk_size: int = 512           # Token 数
    chunk_overlap: int = 50
    similarity_threshold: float = 0.8  # 语义分块合并阈值
    bm25_top_k: int = 3
    vector_top_k: int = 3
    final_top_k: int = 5
    vector_min_score: float = 0.5
    
    # 短期记忆
    max_context_tokens: int = 4000  # 滑动窗口 Token 上限
    summary_keep_rounds: int = 3    # 保留最近 N 轮原话
    
    # 长期记忆
    long_term_memory_top_k: int = 3
    
    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "team_knowledge"
    
    # SQLite
    database_url: str = "sqlite+aiosqlite:///./app.db"

    class Config:
        env_file = ".env"

settings = Settings()
```

### 4.3 数据库模型（models/）

**document.py**
```python
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from database import Base

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50))          # pdf/docx/md/txt
    description = Column(Text)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="processing")  # processing/ready/error
    created_at = Column(DateTime, server_default=func.now())
```

**memory.py**
```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, func
from database import Base

class LongTermMemory(Base):
    __tablename__ = "long_term_memories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False)      # 记忆键，如 "preference"
    value = Column(Text, nullable=False)           # 记忆值
    embedding = Column(Text)                       # JSON 序列化的向量（用于语义搜索）
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

**conversation.py**
```python
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from database import Base

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), default="default")
    title = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)      # user/assistant/system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

### 4.4 核心服务实现

#### 4.4.1 text_splitter.py（语义分块）

实现逻辑：
1. 先用 `tiktoken` 按 `chunk_size` Token 数做基础切分（`TokenTextSplitter`）
2. 对相邻块计算 cosine 相似度
3. 相似度 ≥ `similarity_threshold` 且合并后不超过 `max_tokens` → 合并
4. 否则另起新块（加入 `overlap_tokens` 重叠保证上下文）

```python
import json
import math
import tiktoken
from openai import AsyncOpenAI
from config import settings

def count_tokens(text: str) -> int:
    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    return len(enc.encode(text))

def split_by_token(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按 Token 数基础切分"""
    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = enc.decode(tokens[start:end])
        chunks.append(chunk_text)
        start += chunk_size - overlap
    return chunks

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

async def semantic_split(text: str, client: AsyncOpenAI) -> list[str]:
    """
    语义分块：先基础切分，再根据相似度合并相邻块
    """
    base_chunks = split_by_token(text, settings.chunk_size // 4, settings.chunk_overlap)
    if len(base_chunks) <= 1:
        return base_chunks

    # 批量向量化
    response = await client.embeddings.create(
        input=base_chunks,
        model=settings.embedding_model
    )
    embeddings = [item.embedding for item in response.data]

    # 语义合并
    semantic_chunks = []
    current_block = base_chunks[0]
    current_tokens = count_tokens(current_block)

    for i in range(1, len(base_chunks)):
        sim = cosine_similarity(embeddings[i-1], embeddings[i])
        next_tokens = count_tokens(base_chunks[i])
        if sim >= settings.similarity_threshold and (current_tokens + next_tokens) <= settings.chunk_size:
            current_block += "\n" + base_chunks[i]
            current_tokens += next_tokens
        else:
            semantic_chunks.append(current_block)
            current_block = base_chunks[i]
            current_tokens = next_tokens

    semantic_chunks.append(current_block)
    return semantic_chunks
```

#### 4.4.2 bm25_retriever.py（BM25 关键词检索）

```python
from rank_bm25 import BM25Okapi
import re

def tokenize_chinese(text: str) -> list[str]:
    """简单分词：英文按空格，中文按字"""
    text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text.lower())
    tokens = []
    for word in text.split():
        if re.search(r'[\u4e00-\u9fff]', word):
            tokens.extend(list(word))
        else:
            tokens.append(word)
    return [t for t in tokens if t.strip()]

class BM25Retriever:
    def __init__(self, corpus: list[str]):
        self.corpus = corpus
        tokenized = [tokenize_chinese(doc) for doc in corpus]
        self.bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: str, top_k: int) -> list[tuple[str, float]]:
        query_tokens = tokenize_chinese(query)
        scores = self.bm25.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score > 0:
                results.append((self.corpus[idx], score))
        return results
```

#### 4.4.3 embedding_service.py（向量化 + ChromaDB）

```python
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import AsyncOpenAI
from config import settings

chroma_client = chromadb.PersistentClient(
    path=settings.chroma_persist_dir,
    settings=ChromaSettings(anonymized_telemetry=False)
)
collection = chroma_client.get_or_create_collection(
    name=settings.chroma_collection_name,
    metadata={"hnsw:space": "cosine"}
)

async def embed_texts(texts: list[str], client: AsyncOpenAI) -> list[list[float]]:
    """批量文本向量化"""
    if not texts:
        return []
    response = await client.embeddings.create(input=texts, model=settings.embedding_model)
    return [item.embedding for item in response.data]

async def add_chunks_to_store(doc_id: int, chunks: list[str], client: AsyncOpenAI):
    """将文档分块写入 ChromaDB"""
    embeddings = await embed_texts(chunks, client)
    ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

async def vector_search(query: str, client: AsyncOpenAI, top_k: int, min_score: float) -> list[str]:
    """向量语义检索"""
    query_embedding = (await embed_texts([query], client))[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "distances"]
    )
    chunks = []
    for doc, distance in zip(results["documents"][0], results["distances"][0]):
        score = 1 - distance   # cosine distance → similarity
        if score >= min_score:
            chunks.append(doc)
    return chunks

def get_all_chunks() -> list[str]:
    """获取所有存储的文本块（用于 BM25）"""
    result = collection.get(include=["documents"])
    return result["documents"] or []
```

#### 4.4.4 rag_service.py（混合检索 + Query Rewriting + Prompt 构建）

```python
from openai import AsyncOpenAI
from config import settings
from utils.bm25_retriever import BM25Retriever
from services.embedding_service import vector_search, get_all_chunks

QUERY_REWRITE_PROMPT = """
你是一个检索优化助手。
用户原始问题：{query}
对话历史摘要：{context}

请将用户的问题改写为更适合检索的独立问题（如有指代词，请补全指代内容）。
直接输出改写后的问题，不要解释。
"""

RAG_PROMPT_TEMPLATE = """
你是一个团队智能助理，请基于以下参考资料回答用户问题。
如果资料中没有相关信息，请如实说明，不要编造。

=== 参考资料 ===
{context}
=================

{memory_context}

用户问题：{query}
"""

async def rewrite_query(query: str, context_summary: str, client: AsyncOpenAI) -> str:
    """Query Rewriting：结合上下文改写用户问题"""
    prompt = QUERY_REWRITE_PROMPT.format(query=query, context=context_summary)
    response = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

async def hybrid_retrieve(query: str, client: AsyncOpenAI) -> list[str]:
    """
    混合检索：向量检索 + BM25 关键词检索，结果合并去重
    """
    # 1. 向量检索
    vector_results = await vector_search(
        query, client,
        top_k=settings.vector_top_k,
        min_score=settings.vector_min_score
    )
    
    # 2. BM25 检索
    all_chunks = get_all_chunks()
    bm25_results = []
    if all_chunks:
        retriever = BM25Retriever(all_chunks)
        bm25_results = [text for text, _ in retriever.retrieve(query, settings.bm25_top_k)]
    
    # 3. 合并去重，向量结果优先
    seen = set()
    merged = []
    for chunk in vector_results + bm25_results:
        if chunk not in seen:
            seen.add(chunk)
            merged.append(chunk)
    
    return merged[:settings.final_top_k]

def build_rag_prompt(query: str, chunks: list[str], memory_context: str) -> str:
    if chunks:
        context = "\n\n---\n\n".join(
            f"[{i+1}] {chunk}" for i, chunk in enumerate(chunks)
        )
    else:
        context = "（知识库中暂无相关内容）"
    
    memory_section = ""
    if memory_context:
        memory_section = f"\n=== 用户个人偏好/记忆 ===\n{memory_context}\n========================\n"
    
    return RAG_PROMPT_TEMPLATE.format(
        context=context,
        memory_context=memory_section,
        query=query
    )
```

#### 4.4.5 memory_service.py（短期记忆 + 长期记忆）

```python
import json
import math
import re
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.memory import LongTermMemory
from models.conversation import Message
from config import settings

# ============ 短期记忆（滑动窗口 + 摘要压缩）============

SUMMARY_PROMPT = """
请对以下AI助手和用户的对话历史进行摘要，要求：
1. 简洁明了，控制在100-200字，只保留核心信息
2. 不要遗漏重要细节（如用户提到的名称、需求、关键结果）
3. 语言口语化，符合对话上下文逻辑
4. 不要添加额外内容，只基于提供的对话生成摘要

对话历史：
{dialog_text}
"""

def count_tokens_approx(text: str) -> int:
    """近似 Token 计数（英文约4字/token，中文约2字/token）"""
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    others = len(text) - chinese
    return chinese // 2 + others // 4

class ShortTermMemory:
    """
    短期记忆管理：
    - 保存当前会话的消息历史
    - Token 超限时生成摘要，压缩早期对话
    """
    def __init__(self, max_tokens: int = settings.max_context_tokens):
        self.max_tokens = max_tokens
        self.history: list[dict] = []   # [{role, content}, ...]
        self.summary: str = ""          # 早期对话摘要
    
    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
    
    def get_total_tokens(self) -> int:
        return sum(count_tokens_approx(m["content"]) for m in self.history)
    
    async def maybe_compress(self, client: AsyncOpenAI):
        """当 Token 超限，压缩最早的 N 轮对话"""
        while self.get_total_tokens() > self.max_tokens and len(self.history) > 4:
            # 取出最旧的 2 条（1 轮对话）
            old_messages = self.history[:2]
            self.history = self.history[2:]
            dialog_text = "\n".join(
                f"{'用户' if m['role']=='user' else 'AI'}：{m['content']}"
                for m in old_messages
            )
            response = await client.chat.completions.create(
                model=settings.chat_model,
                messages=[{
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(dialog_text=dialog_text)
                }],
                max_tokens=300,
                temperature=0.3
            )
            new_summary = response.choices[0].message.content.strip()
            self.summary = (self.summary + "\n" + new_summary).strip() if self.summary else new_summary
    
    def build_context_messages(self) -> list[dict]:
        """构建发送给 LLM 的完整上下文"""
        messages = []
        if self.summary:
            messages.append({
                "role": "system",
                "content": f"以下是本次会话早期内容的摘要，供参考：\n{self.summary}"
            })
        messages.extend(self.history)
        return messages
    
    def get_summary_for_query_rewrite(self) -> str:
        return self.summary or "（无历史对话摘要）"

# ============ 长期记忆 ============

CORE_FIELDS = ["name", "preference", "dietary_restriction", "hobby", "work_style", "language_preference"]
DUPLICATE_THRESHOLD = 0.90

EXTRACT_MEMORY_PROMPT = """
分析以下对话，提取用户透露的个人信息/偏好，以JSON格式输出。
只提取明确的信息，不要推断。如果某字段无信息，值设为null。

字段说明：
- name: 用户姓名
- preference: 用户偏好（如回答格式、语言风格等）
- dietary_restriction: 饮食限制
- hobby: 兴趣爱好
- work_style: 工作习惯
- language_preference: 语言偏好（中文/英文等）

对话内容：
{dialog}

只输出JSON，格式：{"name": null, "preference": null, ...}
"""

def cosine_similarity_simple(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a*a for a in v1))
    n2 = math.sqrt(sum(b*b for b in v2))
    return dot / (n1 * n2) if n1 and n2 else 0.0

async def search_long_term_memories(
    user_id: str, query: str, client: AsyncOpenAI,
    db: AsyncSession, top_k: int = settings.long_term_memory_top_k
) -> list[str]:
    """语义检索长期记忆"""
    result = await db.execute(
        select(LongTermMemory).where(LongTermMemory.user_id == user_id)
    )
    memories = result.scalars().all()
    if not memories:
        return []
    
    # 向量化查询
    q_resp = await client.embeddings.create(input=[query], model=settings.embedding_model)
    query_vec = q_resp.data[0].embedding
    
    # 计算相似度
    scored = []
    for mem in memories:
        if mem.embedding:
            mem_vec = json.loads(mem.embedding)
            sim = cosine_similarity_simple(query_vec, mem_vec)
            scored.append((sim, f"{mem.key}: {mem.value}"))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:top_k]]

async def extract_and_save_memories(
    user_id: str, user_input: str, assistant_response: str,
    client: AsyncOpenAI, db: AsyncSession
):
    """从对话中提取并保存长期记忆"""
    dialog = f"用户：{user_input}\nAI：{assistant_response}"
    try:
        resp = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": EXTRACT_MEMORY_PROMPT.format(dialog=dialog)}],
            max_tokens=300,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        extracted = json.loads(resp.choices[0].message.content)
    except Exception:
        return
    
    for key in CORE_FIELDS:
        value = extracted.get(key)
        if not value or str(value).lower() in ("null", "none", ""):
            continue
        value = str(value).strip()
        
        # 去重检查
        existing = await db.execute(
            select(LongTermMemory).where(
                LongTermMemory.user_id == user_id,
                LongTermMemory.key == key
            )
        )
        existing_memories = existing.scalars().all()
        
        # 向量化新记忆
        new_text = f"{key}: {value}"
        emb_resp = await client.embeddings.create(input=[new_text], model=settings.embedding_model)
        new_vec = emb_resp.data[0].embedding
        
        is_duplicate = False
        for mem in existing_memories:
            if mem.embedding:
                old_vec = json.loads(mem.embedding)
                if cosine_similarity_simple(new_vec, old_vec) >= DUPLICATE_THRESHOLD:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            db.add(LongTermMemory(
                user_id=user_id,
                key=key,
                value=value,
                embedding=json.dumps(new_vec)
            ))
    
    await db.commit()
```

#### 4.4.6 document_service.py（文档上传与处理）

```python
import io
import PyPDF2
import docx
from fastapi import UploadFile
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from models.document import Document
from services.embedding_service import add_chunks_to_store
from utils.text_splitter import semantic_split

async def parse_document(file: UploadFile) -> str:
    """解析上传的文档，返回纯文本"""
    content = await file.read()
    filename = file.filename.lower()
    
    if filename.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif filename.endswith(".docx"):
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(para.text for para in doc.paragraphs)
    elif filename.endswith((".md", ".txt")):
        return content.decode("utf-8", errors="ignore")
    else:
        return content.decode("utf-8", errors="ignore")

async def upload_document(
    file: UploadFile, description: str,
    client: AsyncOpenAI, db: AsyncSession
) -> Document:
    """上传文档：解析 → 语义分块 → 向量化 → 存入 ChromaDB"""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "txt"
    
    # 保存文档记录
    doc = Document(filename=file.filename, doc_type=ext, description=description, status="processing")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    try:
        text = await parse_document(file)
        chunks = await semantic_split(text, client)
        await add_chunks_to_store(doc.id, chunks, client)
        doc.chunk_count = len(chunks)
        doc.status = "ready"
    except Exception as e:
        doc.status = "error"
    
    await db.commit()
    await db.refresh(doc)
    return doc
```

#### 4.4.7 code_review_service.py（AI Code Review）

```python
from openai import AsyncOpenAI
from config import settings

CODE_REVIEW_SYSTEM_PROMPT = """
# AI 代码评审规则

## 评审角色定位
作为资深架构师/技术专家进行代码评审，分析代码变更并提供专业的评审意见。

## 问题分级
- 🔴 **Critical（必须修复）**：安全漏洞、严重性能问题、数据一致性问题、线程安全问题、空指针
- 🟡 **Warning（建议修复）**：代码质量问题、潜在性能隐患、可维护性问题
- 🔵 **Info（优化建议）**：代码风格改进、最佳实践建议、架构优化建议

## 评审维度
1. 代码质量：逻辑清晰、命名规范、单一职责、注释适当
2. 安全性：输入校验、权限控制、敏感数据加密、SQL注入防护
3. 可维护性：高内聚低耦合、设计模式、代码复用
4. 性能：N+1查询、索引使用、缓存策略、批量操作
5. 异常处理：完整的错误处理、事务边界

## 输出格式（必须严格遵守）

### 评审概览
- 变更意图：[简要说明]
- 整体评分：[X/5分]

### 🔴 Critical 问题（必须修复）
[若无则写"无"]

**问题1**
- 位置：[文件名:行号 或 代码片段描述]
- 问题描述：[具体问题说明]
- 影响：[潜在影响分析]
- 建议：[具体改进方案]

### 🟡 Warning 问题（建议修复）
[若无则写"无"]

**问题1**
- 位置：[...]
- 问题描述：[...]
- 建议：[...]

### 🔵 Info 优化建议
[若无则写"无"]

### 总结
[整体评价和改进方向]
"""

async def stream_code_review(code_diff: str, language: str, client: AsyncOpenAI):
    """流式输出代码审查报告"""
    user_message = f"""
请对以下{'代码变更（diff）' if language == 'diff' else f'{language}代码'}进行 Code Review：

```{language}
{code_diff}
```
"""
    
    stream = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": CODE_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        stream=True,
        temperature=0.3,
        max_tokens=3000
    )
    
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
```

### 4.5 路由实现

#### 4.5.1 chat_router.py（SSE 流式问答）

```python
import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from database import get_db
from config import settings
from services.rag_service import hybrid_retrieve, rewrite_query, build_rag_prompt
from services.memory_service import (
    ShortTermMemory, search_long_term_memories,
    extract_and_save_memories
)
from services.llm_service import get_openai_client

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 内存中维护短期记忆（session_id → ShortTermMemory）
session_memories: dict[str, ShortTermMemory] = {}

@router.get("/stream")
async def chat_stream(
    query: str = Query(..., description="用户问题"),
    session_id: str = Query(default="", description="会话ID，空则新建"),
    user_id: str = Query(default="default"),
    db: AsyncSession = Depends(get_db)
):
    """
    SSE 流式问答接口
    流程：Query Rewriting → 混合检索 → 长期记忆检索 → 构建Prompt → 流式LLM输出 → 保存记忆
    """
    if not session_id:
        session_id = str(uuid.uuid4())
    
    if session_id not in session_memories:
        session_memories[session_id] = ShortTermMemory()
    
    short_mem = session_memories[session_id]
    client = get_openai_client()

    async def generate():
        # 1. 短期记忆压缩检查
        await short_mem.maybe_compress(client)
        
        # 2. Query Rewriting
        rewritten_query = await rewrite_query(
            query, short_mem.get_summary_for_query_rewrite(), client
        )
        
        # 3. 混合检索
        chunks = await hybrid_retrieve(rewritten_query, client)
        
        # 4. 长期记忆检索
        long_term_memories = await search_long_term_memories(user_id, query, client, db)
        memory_context = "\n".join(long_term_memories) if long_term_memories else ""
        
        # 5. 构建 RAG Prompt
        rag_prompt = build_rag_prompt(rewritten_query, chunks, memory_context)
        
        # 6. 组装消息上下文
        context_messages = short_mem.build_context_messages()
        context_messages.append({"role": "user", "content": rag_prompt})
        
        # 7. 流式 LLM 输出
        full_response = ""
        yield f"data: {{\"session_id\": \"{session_id}\"}}\n\n"
        
        stream = await client.chat.completions.create(
            model=settings.chat_model,
            messages=context_messages,
            stream=True,
            temperature=0.7,
            max_tokens=2000
        )
        
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                full_response += delta.content
                import json
                yield f"data: {json.dumps({'content': delta.content})}\n\n"
        
        yield "data: [DONE]\n\n"
        
        # 8. 更新短期记忆
        short_mem.add("user", query)
        short_mem.add("assistant", full_response)
        
        # 9. 异步提取长期记忆（后台执行）
        await extract_and_save_memories(user_id, query, full_response, client, db)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )

@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """清除会话的短期记忆"""
    session_memories.pop(session_id, None)
    return {"message": "Session cleared"}

@router.get("/memories/{user_id}")
async def get_user_memories(user_id: str, db: AsyncSession = Depends(get_db)):
    """获取用户长期记忆列表"""
    from sqlalchemy import select
    from models.memory import LongTermMemory
    result = await db.execute(
        select(LongTermMemory).where(LongTermMemory.user_id == user_id)
    )
    memories = result.scalars().all()
    return [{"id": m.id, "key": m.key, "value": m.value, "created_at": str(m.created_at)} for m in memories]
```

#### 4.5.2 document_router.py

```python
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.document import Document
from services.document_service import upload_document
from services.llm_service import get_openai_client

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db)
):
    client = get_openai_client()
    doc = await upload_document(file, description, client, db)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status, "chunk_count": doc.chunk_count}

@router.get("/")
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return [{"id": d.id, "filename": d.filename, "doc_type": d.doc_type,
             "description": d.description, "status": d.status,
             "chunk_count": d.chunk_count, "created_at": str(d.created_at)} for d in docs]

@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    # 同时清除 ChromaDB 中该文档的向量（通过 metadata 过滤删除）
    from services.embedding_service import collection
    collection.delete(where={"doc_id": doc_id})
    return {"message": "Deleted"}
```

#### 4.5.3 code_review_router.py

```python
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from services.code_review_service import stream_code_review
from services.llm_service import get_openai_client

router = APIRouter(prefix="/api/code-review", tags=["code-review"])

@router.post("/stream")
async def review_stream(
    code: str = Form(default=""),
    language: str = Form(default="diff"),
    file: UploadFile = File(default=None)
):
    """流式 Code Review（支持直接输入或上传 diff 文件）"""
    client = get_openai_client()
    
    if file:
        content = await file.read()
        code_content = content.decode("utf-8", errors="ignore")
    else:
        code_content = code
    
    async def generate():
        async for chunk in stream_code_review(code_content, language, client):
            import json
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*"}
    )
```

#### 4.5.4 llm_service.py

```python
from openai import AsyncOpenAI
from config import settings

def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url
    )
```

### 4.6 main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_tables
from routers import document_router, chat_router, code_review_router

app = FastAPI(title="AI Team Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.on_event("startup")
async def startup():
    await create_tables()

app.include_router(document_router.router)
app.include_router(chat_router.router)
app.include_router(code_review_router.router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

### 4.7 database.py

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with SessionLocal() as session:
        yield session

async def create_tables():
    from models import document, memory, conversation  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

---

## 五、前端实现规范

### 5.1 package.json 依赖

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.0",
    "axios": "^1.7.2",
    "zustand": "^4.5.2",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0",
    "react-syntax-highlighter": "^15.5.0",
    "lucide-react": "^0.378.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.4.5",
    "vite": "^5.2.11",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^3.4.3",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38"
  }
}
```

### 5.2 vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

### 5.3 tailwind.config.js

```javascript
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d'
        }
      }
    }
  },
  plugins: []
}
```

### 5.4 全局类型定义（types/index.ts）

```typescript
export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
}

export interface Conversation {
  session_id: string
  messages: Message[]
  isStreaming: boolean
}

export interface Document {
  id: number
  filename: string
  doc_type: string
  description: string
  status: 'processing' | 'ready' | 'error'
  chunk_count: number
  created_at: string
}

export interface LongTermMemory {
  id: number
  key: string
  value: string
  created_at: string
}

export interface ReviewReport {
  content: string
  isStreaming: boolean
}
```

### 5.5 状态管理（store/chatStore.ts）

```typescript
import { create } from 'zustand'
import { Message, LongTermMemory } from '../types'
import { v4 as uuidv4 } from 'uuid'

interface ChatStore {
  sessionId: string
  userId: string
  messages: Message[]
  isStreaming: boolean
  longTermMemories: LongTermMemory[]
  
  setSessionId: (id: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  appendToLastAssistant: (content: string) => void
  setStreaming: (val: boolean) => void
  clearSession: () => void
  setMemories: (memories: LongTermMemory[]) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  sessionId: uuidv4(),
  userId: 'default',
  messages: [],
  isStreaming: false,
  longTermMemories: [],
  
  setSessionId: (id) => set({ sessionId: id }),
  addMessage: (msg) => set((state) => ({
    messages: [...state.messages, { ...msg, id: uuidv4(), timestamp: Date.now() }]
  })),
  appendToLastAssistant: (content) => set((state) => {
    const msgs = [...state.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') {
      msgs[msgs.length - 1] = { ...last, content: last.content + content }
    }
    return { messages: msgs }
  }),
  setStreaming: (val) => set({ isStreaming: val }),
  clearSession: () => set({ messages: [], sessionId: uuidv4() }),
  setMemories: (memories) => set({ longTermMemories: memories })
}))
```

### 5.6 页面与组件规范

#### Layout.tsx（整体布局）
- 左侧固定侧边栏，宽度 240px，深色背景 `bg-gray-900`
- 导航项：💬 智能问答、📚 知识库、🔍 Code Review、⚙️ 设置
- 主内容区 `flex-1 overflow-hidden`

#### ChatPage.tsx（智能问答）
实现要点：
1. 顶部显示当前会话 ID，有"新建对话"按钮
2. 消息列表区，用户消息右对齐（蓝色气泡），AI 消息左对齐（灰色气泡，支持 Markdown 渲染）
3. AI 回答中光标闪烁动画（`animate-pulse`）
4. 底部输入框 + 发送按钮，按 Enter 发送，Shift+Enter 换行
5. 右侧可折叠面板展示"长期记忆"列表（key-value 卡片形式）
6. SSE 实现（使用原生 `EventSource` 或 `fetch` + `ReadableStream`）

```typescript
// chatApi.ts
export async function streamChat(
  query: string, sessionId: string, userId: string,
  onChunk: (content: string) => void,
  onDone: (newSessionId?: string) => void
) {
  const url = `/api/chat/stream?query=${encodeURIComponent(query)}&session_id=${sessionId}&user_id=${userId}`
  const response = await fetch(url)
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') { onDone(); return }
        try {
          const parsed = JSON.parse(data)
          if (parsed.session_id) onDone(parsed.session_id)
          if (parsed.content) onChunk(parsed.content)
        } catch {}
      }
    }
  }
}
```

#### DocumentsPage.tsx（知识库管理）
- 顶部"上传文档"按钮，点击弹出上传对话框
- 文档列表：表格展示（文件名、类型、描述、分块数、状态、上传时间、操作）
- 状态 Badge：`processing`（黄色旋转图标）、`ready`（绿色）、`error`（红色）
- 删除文档有确认弹框
- 支持拖拽上传

#### CodeReviewPage.tsx（Code Review）
- 左侧：代码输入区（Monaco 编辑器风格的 textarea + 语言选择下拉）、文件上传按钮（接受 `.diff` 文件）、"开始审查"按钮
- 右侧：审查报告展示区（Markdown 渲染，支持代码高亮）
- 报告分区域用颜色区分：🔴 红色边框（Critical）、🟡 黄色边框（Warning）、🔵 蓝色边框（Info）
- 报告底部有"下载 Markdown 报告"按钮（触发浏览器下载）
- 整个页面支持键盘快捷键：`Ctrl+Enter` 触发审查

#### SettingsPage.tsx（设置）
- 表单字段：
  - OpenAI API Key（密码输入框）
  - API Base URL（支持自定义，兼容 DashScope、本地模型）
  - Chat Model（下拉：gpt-4o-mini / gpt-4o / qwen-plus / 自定义）
  - Embedding Model（下拉：text-embedding-3-small / text-embedding-v3 / 自定义）
- "测试连接"按钮（调用 `/api/health` 和 LLM 连通性测试）
- 保存时写入 localStorage，后端通过 `/api/settings` 接口持久化到 `.env`

---

## 六、API 接口完整列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/documents/upload` | 上传文档（multipart/form-data） |
| GET | `/api/documents/` | 获取文档列表 |
| DELETE | `/api/documents/{doc_id}` | 删除文档 |
| GET | `/api/chat/stream` | SSE 流式问答（Query 参数：query, session_id, user_id） |
| DELETE | `/api/chat/session/{session_id}` | 清除会话 |
| GET | `/api/chat/memories/{user_id}` | 获取用户长期记忆 |
| DELETE | `/api/chat/memories/{memory_id}` | 删除单条长期记忆 |
| POST | `/api/code-review/stream` | SSE 流式 Code Review（form: code/file, language） |
| POST | `/api/settings` | 更新配置（API Key 等） |
| GET | `/api/settings` | 获取当前配置（隐藏敏感字段） |

---

## 七、UI 设计规范

### 配色主题（深色模式为主，支持切换）

**深色主题**：
- 背景 `#0f1117`，侧边栏 `#161b22`
- 卡片 `#1c2128`，边框 `#30363d`
- 主色调：绿色 `#3fb950`（类 GitHub Dark）
- 文字：`#e6edf3`（主）、`#8b949e`（次）

**浅色主题**：
- 背景 `#ffffff`，侧边栏 `#f6f8fa`
- 主色调：`#1a7f37`

### 字体
- 系统字体栈：`-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif`
- 代码字体：`"JetBrains Mono", "Fira Code", Consolas, monospace`

### 组件规范
- 圆角：`rounded-md`（4px）到 `rounded-xl`（12px）
- 阴影：仅 Card 和 Dialog 使用 `shadow-md`
- 过渡：`transition-all duration-200`
- 消息气泡：用户气泡 `bg-blue-600 text-white rounded-2xl rounded-br-sm`，AI 气泡 `bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-sm`
- Code Review Critical：左边框 `border-l-4 border-red-500 bg-red-50 dark:bg-red-900/20`
- Code Review Warning：左边框 `border-l-4 border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20`
- Code Review Info：左边框 `border-l-4 border-blue-500 bg-blue-50 dark:bg-blue-900/20`

---

## 八、环境变量（.env.example）

```env
# LLM 配置（支持 OpenAI / DashScope / 本地模型）
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.openai.com/v1
CHAT_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# RAG 参数（可选，有默认值）
CHUNK_SIZE=512
VECTOR_MIN_SCORE=0.5
BM25_TOP_K=3
VECTOR_TOP_K=3
FINAL_TOP_K=5

# 数据存储
CHROMA_PERSIST_DIR=./chroma_db
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

---

## 九、docker-compose.yml

```yaml
version: '3.8'
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend/.env:/app/.env
      - ./backend/chroma_db:/app/chroma_db
      - ./backend/app.db:/app/app.db
    environment:
      - PYTHONUNBUFFERED=1
    
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - backend
```

**backend/Dockerfile**：
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**frontend/Dockerfile**：
```dockerfile
FROM node:20-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

## 十、启动说明（README.md 内容）

### 本地开发启动

```bash
# 后端
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填写 API Key
uvicorn main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

### Docker 启动

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env
docker-compose up -d
# 访问 http://localhost:3000
```

---

## 十一、实现优先级与注意事项

### 优先级
1. **P0（核心功能）**：
   - 后端：文档上传 → ChromaDB 存储 → 混合检索 → 流式问答（SSE）
   - 前端：聊天页面流式展示、文档上传页面
   
2. **P1（增强功能）**：
   - 短期记忆滑动窗口 + 摘要压缩
   - 长期记忆提取 + 存储 + 检索
   - Query Rewriting
   
3. **P2（完善功能）**：
   - AI Code Review 页面
   - 设置页面
   - 深色/浅色模式切换

### 关键注意事项

1. **SSE 流式输出**：前端用 `fetch` + `ReadableStream` 而非 `EventSource`（因为 EventSource 不支持 POST），GET 请求参数用 URL Query String 传递。

2. **ChromaDB 并发**：ChromaDB 本地模式不支持多进程，FastAPI 启动时用单 worker：`uvicorn main:app --workers 1`。

3. **Token 计算**：使用 `tiktoken` 精确计算，`count_tokens_approx` 仅用于快速估算。

4. **BM25 性能**：每次检索都要从 ChromaDB 加载所有文档块，数据量大时考虑增加缓存（内存中保存 `BM25Retriever` 实例，文档更新时刷新）。

5. **安全性**：API Key 不要在前端硬编码，通过后端 `/api/settings` 接口保存到 `.env` 文件，前端只存 localStorage 的哈希或空白显示。

6. **Markdown 渲染**：AI 回答支持完整的 GFM Markdown（表格、代码块、列表），Code Review 报告同样用 `react-markdown + remark-gfm` 渲染。

7. **错误处理**：所有接口有统一的错误响应格式 `{"detail": "错误信息"}`，前端统一弹出 Toast 提示。

