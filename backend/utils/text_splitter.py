import math
from typing import Optional

import tiktoken

from config import settings


def get_encoder():
    return tiktoken.encoding_for_model("gpt-4o-mini")


def count_tokens(text: str) -> int:
    return len(get_encoder().encode(text))


def split_by_token(text: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> list[str]:
    size = chunk_size or settings.chunk_size
    overlap_size = overlap or settings.chunk_overlap
    enc = get_encoder()
    tokens = enc.encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    step = max(1, size - overlap_size)
    start = 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        chunk = enc.decode(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
