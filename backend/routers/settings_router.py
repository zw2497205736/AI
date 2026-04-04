from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import settings
from schemas.chat import ChatSettingsPayload
from services.llm_service import get_openai_client


router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
ALLOWED_KEYS = {
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "OPENAI_BASE_URL",
    "chat_model": "CHAT_MODEL",
    "embedding_model": "EMBEDDING_MODEL",
}


def write_env(payload: ChatSettingsPayload):
    current: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                current[key] = value
    for field, env_key in ALLOWED_KEYS.items():
        value = getattr(payload, field)
        if value is not None:
            current[env_key] = value
    content = "\n".join(f"{key}={value}" for key, value in current.items()) + "\n"
    ENV_PATH.write_text(content, encoding="utf-8")


@router.get("")
async def get_settings():
    return {
        "openai_api_key_configured": bool(settings.openai_api_key),
        "openai_base_url": settings.openai_base_url,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
    }


@router.post("")
async def update_settings(payload: ChatSettingsPayload):
    write_env(payload)
    return {"message": "Settings updated"}


@router.get("/test")
async def test_settings():
    client = get_openai_client()
    try:
        await client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        await client.embeddings.create(
            model=settings.embedding_model,
            input=["ping"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"LLM connectivity test failed: {exc}") from exc
    return {"message": "Connection ok"}
