import json
import logging
from typing import AsyncIterator

import httpx
from openai import AsyncOpenAI, OpenAI

from config import settings

logger = logging.getLogger(__name__)


def _build_client(*, api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers={"User-Agent": settings.openai_user_agent},
        timeout=settings.request_timeout,
        max_retries=2,
    )


def get_chat_client() -> AsyncOpenAI:
    return _build_client(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def get_embedding_client() -> AsyncOpenAI:
    return _build_client(
        api_key=settings.embedding_api_key or settings.openai_api_key,
        base_url=settings.embedding_base_url or settings.openai_base_url,
    )


def get_openai_client() -> AsyncOpenAI:
    return get_chat_client()


def get_embedding_sync_client() -> OpenAI:
    return OpenAI(
        api_key=settings.embedding_api_key or settings.openai_api_key,
        base_url=settings.embedding_base_url or settings.openai_base_url,
        default_headers={"User-Agent": settings.openai_user_agent},
        timeout=settings.request_timeout,
        max_retries=2,
    )


def _build_chat_messages(input_messages: list[dict], instructions: str | None = None) -> list[dict]:
    messages: list[dict] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    for message in input_messages:
        role = str(message.get("role", "user"))
        if role not in {"system", "user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": str(message.get("content", ""))})
    return messages


def _extract_chat_content(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                texts.append(str(item["text"]))
                continue
            if item.get("type") == "output_text" and item.get("text"):
                texts.append(str(item["text"]))
        text = "".join(texts).strip()
        if text:
            return text
    return ""


async def _chat_completions_request(payload: dict, timeout: int | None = None):
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    logger.info(
        "Calling chat completions: url=%s model=%s stream=%s max_tokens=%s",
        url,
        payload.get("model"),
        payload.get("stream", False),
        payload.get("max_tokens"),
    )
    async with httpx.AsyncClient(timeout=timeout or settings.request_timeout) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
                "User-Agent": settings.openai_user_agent,
            },
            json=payload,
        )
    if response.is_error:
        logger.error(
            "Chat Completions API error: status=%s body=%s",
            response.status_code,
            response.text[:2000],
        )
    response.raise_for_status()
    return response.json()


async def create_text_response(
    *,
    model: str,
    input_messages: list[dict],
    instructions: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    text_format: dict | None = None,
) -> str:
    payload: dict = {
        "model": model,
        "messages": _build_chat_messages(input_messages, instructions),
    }
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens
    if text_format and text_format.get("format", {}).get("type") == "json_object":
        payload["response_format"] = {"type": "json_object"}
    data = await _chat_completions_request(payload)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    text = _extract_chat_content(message)
    if text:
        return text
    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        logger.warning("Model returned reasoning_content without final content; suppressing reasoning output")
    return ""


async def stream_text_response(
    *,
    model: str,
    input_messages: list[dict],
    instructions: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> AsyncIterator[str]:
    payload: dict = {
        "model": model,
        "messages": _build_chat_messages(input_messages, instructions),
        "stream": True,
    }
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
                "User-Agent": settings.openai_user_agent,
            },
            json=payload,
        ) as response:
            if response.is_error:
                body = await response.aread()
                logger.error(
                    "Chat Completions stream API error: status=%s body=%s",
                    response.status_code,
                    body.decode("utf-8", errors="ignore")[:2000],
                )
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content
