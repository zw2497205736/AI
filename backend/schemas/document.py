from pydantic import BaseModel
from typing import Optional


class DocumentResponse(BaseModel):
    id: int
    filename: str
    doc_type: Optional[str] = None
    description: Optional[str] = None
    status: str
    chunk_count: int
    created_at: str
    error_message: Optional[str] = None
