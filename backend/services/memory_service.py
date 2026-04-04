import json
import math
import re

from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.memory import LongTermMemory


SUMMARY_PROMPT = """
请对以下对话做简洁摘要，保留用户需求、限制条件和关键结论。

对话：
{dialog_text}
"""

EXTRACT_MEMORY_PROMPT = """
分析以下对话，提取用户明确表达的个人偏好或稳定信息。
只输出 JSON，不要解释。

字段：
- name
- preference
- dietary_restriction
- hobby
- work_style
- language_preference

对话：
{dialog}
"""

CORE_FIELDS = ["name", "preference", "dietary_restriction", "hobby", "work_style", "language_preference"]


def normalize_memory_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(items)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            key_text = str(key).strip()
            item_text = str(item).strip()
            if key_text and item_text:
                parts.append(f"{key_text}: {item_text}")
        return "；".join(parts)

    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if parsed != value:
            return normalize_memory_value(parsed)
    except Exception:
        pass

    if text.startswith("[") and text.endswith("]"):
        stripped = text[1:-1].strip().strip("'").strip('"')
        return stripped
    return text


def canonicalize_memory(key: str, value: str) -> tuple[str, str]:
    normalized_key = key.strip().lower()
    normalized_value = normalize_memory_value(value)
    compact = normalized_value.strip().lower()

    if normalized_key == "language_preference":
        if compact in {"中文", "chinese", "zh", "zh-cn", "mandarin"}:
            return normalized_key, "中文"
        if compact in {"英文", "english", "en", "en-us"}:
            return normalized_key, "英文"

    return normalized_key, normalized_value


def is_redundant_memory(key: str, value: str, existing_pairs: set[tuple[str, str]]) -> bool:
    compact = value.strip().lower()
    if key == "preference":
        if ("language_preference", "中文") in existing_pairs and ("中文" in value or "chinese" in compact):
            return True
        if ("language_preference", "英文") in existing_pairs and ("英文" in value or "english" in compact):
            return True
    return False


def dedupe_memories(memories: list[LongTermMemory]) -> list[LongTermMemory]:
    normalized_items: list[LongTermMemory] = []
    seen_pairs: set[tuple[str, str]] = set()

    # 优先保留结构化程度更高的记忆，例如 language_preference 优先于 preference。
    def sort_priority(memory: LongTermMemory):
        canonical_key, canonical_value = canonicalize_memory(memory.key, memory.value)
        key_priority = 0 if canonical_key == "language_preference" else 1
        return (key_priority, str(memory.created_at))

    for memory in sorted(memories, key=sort_priority):
        canonical_key, canonical_value = canonicalize_memory(memory.key, memory.value)
        pair = (canonical_key, canonical_value)
        if is_redundant_memory(canonical_key, canonical_value, seen_pairs):
            continue
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        memory.key = canonical_key
        memory.value = canonical_value
        normalized_items.append(memory)

    normalized_items.sort(key=lambda item: str(item.created_at), reverse=True)
    return normalized_items


def count_tokens_approx(text: str) -> int:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    others = len(text) - chinese
    return chinese // 2 + others // 4


class ShortTermMemory:
    def __init__(self, max_tokens: int = settings.max_context_tokens):
        self.max_tokens = max_tokens
        self.history: list[dict[str, str]] = []
        self.summary = ""

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def get_total_tokens(self) -> int:
        return sum(count_tokens_approx(item["content"]) for item in self.history)

    async def maybe_compress(self, client: AsyncOpenAI):
        keep_messages = settings.summary_keep_rounds * 2
        while self.get_total_tokens() > self.max_tokens and len(self.history) > keep_messages:
            compressible = self.history[:-keep_messages]
            if len(compressible) < 2:
                break
            old_messages = compressible[:2]
            self.history = self.history[2:]
            dialog_text = "\n".join(
                f"{'用户' if item['role'] == 'user' else 'AI'}：{item['content']}" for item in old_messages
            )
            response = await client.chat.completions.create(
                model=settings.chat_model,
                messages=[{"role": "user", "content": SUMMARY_PROMPT.format(dialog_text=dialog_text)}],
                max_tokens=200,
                temperature=0.2,
            )
            new_summary = (response.choices[0].message.content or "").strip()
            self.summary = f"{self.summary}\n{new_summary}".strip() if self.summary else new_summary

    def build_context_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.summary:
            messages.append({"role": "system", "content": f"以下是当前会话更早内容的摘要：\n{self.summary}"})
        messages.extend(self.history)
        return messages

    def get_summary_for_query_rewrite(self) -> str:
        return self.summary or "（无历史对话摘要）"

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict):
        memory = cls()
        memory.summary = str(data.get("summary", "") or "")
        history = data.get("history", [])
        if isinstance(history, list):
            memory.history = [
                {
                    "role": str(item.get("role", "")),
                    "content": str(item.get("content", "")),
                }
                for item in history
                if isinstance(item, dict)
            ]
        return memory


def cosine_similarity_simple(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return dot / (n1 * n2) if n1 and n2 else 0.0


async def search_long_term_memories(user_id: str, query: str, client: AsyncOpenAI, db: AsyncSession) -> list[str]:
    result = await db.execute(select(LongTermMemory).where(LongTermMemory.user_id == user_id))
    memories = result.scalars().all()
    if not memories:
        return []
    deduped_memories = dedupe_memories(memories)

    try:
        query_embedding = (await client.embeddings.create(input=[query], model=settings.embedding_model)).data[0].embedding
    except Exception:
        return [f"{memory.key}: {memory.value}" for memory in deduped_memories[: settings.long_term_memory_top_k]]
    scored: list[tuple[float, str]] = []
    for memory in deduped_memories:
        if not memory.embedding:
            continue
        sim = cosine_similarity_simple(query_embedding, json.loads(memory.embedding))
        scored.append((sim, f"{memory.key}: {memory.value}"))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[: settings.long_term_memory_top_k]]


async def extract_and_save_memories(user_id: str, user_input: str, assistant_response: str, client: AsyncOpenAI, db: AsyncSession):
    dialog = f"用户：{user_input}\nAI：{assistant_response}"
    try:
        response = await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": EXTRACT_MEMORY_PROMPT.format(dialog=dialog)}],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        extracted = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return

    for key in CORE_FIELDS:
        value = extracted.get(key)
        normalized_key, normalized = canonicalize_memory(key, value)
        if not normalized or normalized.lower() in {"null", "none", ""}:
            continue
        existing = await db.execute(select(LongTermMemory).where(LongTermMemory.user_id == user_id, LongTermMemory.key == normalized_key))
        existing_memories = existing.scalars().all()
        duplicate_found = False
        for memory in existing_memories:
            _, existing_value = canonicalize_memory(memory.key, memory.value)
            if existing_value == normalized:
                duplicate_found = True
                break
        if duplicate_found or is_redundant_memory(normalized_key, normalized, {(canonicalize_memory(item.key, item.value)) for item in existing_memories}):
            continue
        try:
            embedding = (await client.embeddings.create(input=[f"{normalized_key}: {normalized}"], model=settings.embedding_model)).data[0].embedding
            serialized = json.dumps(embedding)
        except Exception:
            serialized = None
        db.add(LongTermMemory(user_id=user_id, key=normalized_key, value=normalized, embedding=serialized))

    await db.commit()


async def list_memories(user_id: str, db: AsyncSession) -> list[LongTermMemory]:
    result = await db.execute(select(LongTermMemory).where(LongTermMemory.user_id == user_id).order_by(LongTermMemory.created_at.desc()))
    memories = list(result.scalars().all())
    return dedupe_memories(memories)


async def delete_memory(memory_id: int, user_id: str, db: AsyncSession) -> bool:
    result = await db.execute(select(LongTermMemory).where(LongTermMemory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        return False
    if memory.user_id != user_id:
        return False
    await db.execute(delete(LongTermMemory).where(LongTermMemory.id == memory_id))
    await db.commit()
    return True
