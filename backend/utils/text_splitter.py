import math
import re
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


def _normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


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


def split_by_structure(text: str, doc_type: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    if doc_type in {"md", "markdown"}:
        lines = normalized.split("\n")
        chunks: list[str] = []
        current: list[str] = []
        heading_pattern = re.compile(r"^\s{0,3}#{1,6}\s+.+$")
        for line in lines:
            stripped = line.strip()
            if heading_pattern.match(line) and current:
                chunks.append("\n".join(current).strip())
                current = [line]
                continue
            current.append(line)
            if not stripped and current and len(current) >= 8:
                chunks.append("\n".join(current).strip())
                current = []
        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", normalized) if paragraph.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    for paragraph in paragraphs:
        is_heading_like = len(paragraph) <= 40 and not re.search(r"[。！？.!?]", paragraph)
        if is_heading_like and current:
            chunks.append("\n\n".join(current).strip())
            current = [paragraph]
            continue
        current.append(paragraph)
        if len(current) >= 4:
            chunks.append("\n\n".join(current).strip())
            current = []
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def split_by_semantic_boundaries(chunk: str, *, target_tokens: Optional[int] = None) -> list[str]:
    max_tokens = max(220, target_tokens or settings.chunk_size)
    if count_tokens(chunk) <= max_tokens:
        return [chunk.strip()]

    units = re.split(r"(?<=\n\n)|(?<=\n)|(?<=[。！？!?；;])", chunk)
    units = [unit.strip() for unit in units if unit.strip()]
    if not units:
        return [chunk.strip()]

    pieces: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n".join(current + [unit]).strip() if current else unit
        if current and count_tokens(candidate) > max_tokens:
            pieces.append("\n".join(current).strip())
            current = [unit]
            continue
        current.append(unit)
    if current:
        pieces.append("\n".join(current).strip())
    return [piece for piece in pieces if piece]


def merge_small_chunks(chunks: list[str], *, min_tokens: int = 220, max_tokens: Optional[int] = None) -> list[str]:
    upper_bound = max_tokens or settings.chunk_size
    merged: list[str] = []
    current = ""
    for chunk in chunks:
        normalized = chunk.strip()
        if not normalized:
            continue
        if not current:
            current = normalized
            continue
        current_tokens = count_tokens(current)
        chunk_tokens = count_tokens(normalized)
        candidate = current + "\n\n" + normalized
        candidate_tokens = count_tokens(candidate)
        if current_tokens < min_tokens and candidate_tokens <= upper_bound:
            current = candidate
            continue
        if chunk_tokens < min_tokens and candidate_tokens <= upper_bound:
            current = candidate
            continue
        merged.append(current.strip())
        current = normalized
    if current.strip():
        merged.append(current.strip())
    return merged


def enforce_token_limit(chunks: list[str], chunk_size: Optional[int] = None, overlap: Optional[int] = None) -> list[str]:
    limited: list[str] = []
    for chunk in chunks:
        if count_tokens(chunk) <= (chunk_size or settings.chunk_size):
            limited.append(chunk.strip())
            continue
        limited.extend(split_by_token(chunk, chunk_size=chunk_size, overlap=overlap))
    return [chunk for chunk in limited if chunk]


def split_document(text: str, doc_type: str) -> list[str]:
    structure_chunks = split_by_structure(text, doc_type)
    if not structure_chunks:
        return []

    semantic_chunks: list[str] = []
    for chunk in structure_chunks:
        if count_tokens(chunk) <= settings.chunk_size:
            semantic_chunks.append(chunk.strip())
            continue
        semantic_chunks.extend(split_by_semantic_boundaries(chunk, target_tokens=settings.chunk_size))

    merged_chunks = merge_small_chunks(semantic_chunks, min_tokens=max(180, settings.chunk_size // 2), max_tokens=settings.chunk_size)
    final_chunks = enforce_token_limit(merged_chunks, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
    return [chunk for chunk in final_chunks if chunk.strip()]


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)
