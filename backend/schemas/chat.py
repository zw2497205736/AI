from pydantic import BaseModel
from typing import Optional


class MemoryResponse(BaseModel):
    id: int
    key: str
    value: str
    created_at: str


class ChatSettingsPayload(BaseModel):
    openai_api_key: Optional[str] = None
    openai_base_url: str
    chat_model: str
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    embedding_model: str


class ConversationUpdatePayload(BaseModel):
    title: str
