import math
from typing import Optional

import tiktoken

from config import settings

try:
    from langchain_text_splitters import TokenTextSplitter

    HAS_LANGCHAIN = True
except ImportError:
    TokenTextSplitter = None
    HAS_LANGCHAIN = False


def get_encoder():
    return tiktoken.encoding_for_model("gpt-4o-mini")


def count_tokens(text: str) -> int:
    return len(get_encoder().encode(text))


def split_by_token(text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> list[str]:
    size = chunk_size or settings.chunk_size
    overlap_size = overlap or settings.chunk_overlap
    if not HAS_LANGCHAIN or TokenTextSplitter is None:
        token_ids = get_encoder().encode(text)
        if not token_ids:
            return []
        step = max(1, size - overlap_size)
        chunks: list[str] = []
        for start in range(0, len(token_ids), step):
            end = start + size
            chunk = get_encoder().decode(token_ids[start:end]).strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(token_ids):
                break
        return chunks
    splitter = TokenTextSplitter(
        encoding_name=get_encoder().name,
        chunk_size=size,
        chunk_overlap=overlap_size,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
