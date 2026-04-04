import json
from typing import Optional

from redis.asyncio import Redis

from config import settings
from services.memory_service import ShortTermMemory


redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def get_session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"


async def load_short_memory(session_id: str) -> Optional[ShortTermMemory]:
    try:
        raw = await redis_client.get(get_session_key(session_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return ShortTermMemory.from_dict(data)


async def save_short_memory(session_id: str, memory: ShortTermMemory):
    payload = json.dumps(memory.to_dict(), ensure_ascii=False)
    try:
        await redis_client.set(get_session_key(session_id), payload, ex=settings.session_memory_ttl_seconds)
    except Exception:
        return


async def delete_short_memory(session_id: str):
    try:
        await redis_client.delete(get_session_key(session_id))
    except Exception:
        return
