from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import settings
from schemas.chat import ChatSettingsPayload
from services.llm_service import create_text_response, get_embedding_client


router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
ALLOWED_KEYS = {
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "OPENAI_BASE_URL",
    "chat_model": "CHAT_MODEL",
    "embedding_api_key": "EMBEDDING_API_KEY",
    "embedding_base_url": "EMBEDDING_BASE_URL",
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
        "embedding_api_key_configured": bool(settings.embedding_api_key or settings.openai_api_key),
        "embedding_base_url": settings.embedding_base_url or settings.openai_base_url,
        "embedding_model": settings.embedding_model,
    }


@router.post("")
async def update_settings(payload: ChatSettingsPayload):
    write_env(payload)
    return {"message": "Settings updated"}


@router.get("/test")
async def test_settings():
    chat_error = None
    embedding_error = None
    try:
        await create_text_response(
            model=settings.chat_model,
            input_messages=[{"role": "user", "content": "ping"}],
            max_output_tokens=1,
            temperature=0,
        )
    except Exception as exc:
        chat_error = str(exc)

    try:
        embedding_client = get_embedding_client()
        await embedding_client.embeddings.create(
            model=settings.embedding_model,
            input=["ping"],
        )
    except Exception as exc:
        embedding_error = str(exc)

    if chat_error:
        detail = f"Chat connectivity test failed: {chat_error}"
        if embedding_error:
            detail = f"{detail}; Embedding connectivity test failed: {embedding_error}"
        raise HTTPException(status_code=400, detail=detail)

    if embedding_error:
        return {
            "message": "Chat ok, embedding failed",
            "chat_ok": True,
            "embedding_ok": False,
            "embedding_error": embedding_error,
        }

    return {"message": "Connection ok", "chat_ok": True, "embedding_ok": True}
