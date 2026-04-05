import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

import httpx

from config import settings
from models.github_repository import GitHubRepository
from services.auth_service import get_secret_key


def _build_keystream(nonce: bytes, length: int) -> bytes:
    secret = get_secret_key()
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = hmac.new(secret, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def encrypt_github_token(token: str) -> str:
    raw = token.encode("utf-8")
    nonce = secrets.token_bytes(16)
    keystream = _build_keystream(nonce, len(raw))
    encrypted = bytes(a ^ b for a, b in zip(raw, keystream))
    return base64.urlsafe_b64encode(nonce + encrypted).decode("utf-8")


def decrypt_github_token(encrypted_token: str) -> str:
    payload = base64.urlsafe_b64decode(encrypted_token.encode("utf-8"))
    nonce, encrypted = payload[:16], payload[16:]
    keystream = _build_keystream(nonce, len(encrypted))
    raw = bytes(a ^ b for a, b in zip(encrypted, keystream))
    return raw.decode("utf-8")


def verify_github_signature(body: bytes, secret: str, signature_256: str) -> bool:
    if not signature_256.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_256)


def mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}{'*' * (len(token) - 8)}{token[-4:]}"


async def verify_repository_access(repo_owner: str, repo_name: str, token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo_owner}/{repo_name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    response.raise_for_status()
    return response.json()


async def fetch_pull_request(repo: GitHubRepository, pr_number: int) -> dict[str, Any]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/pulls/{pr_number}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    response.raise_for_status()
    return response.json()


async def fetch_pull_request_files(repo: GitHubRepository, pr_number: int) -> list[dict[str, Any]]:
    token = decrypt_github_token(repo.github_token_encrypted)
    files: list[dict[str, Any]] = []
    page = 1
    while len(files) < settings.github_diff_max_files:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            response = await client.get(
                f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/pulls/{pr_number}/files",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                params={"page": page, "per_page": min(100, settings.github_diff_max_files)},
            )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files[: settings.github_diff_max_files]


def build_reviewable_diff(files: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    total_length = 0
    for item in files[: settings.github_diff_max_files]:
        patch = item.get("patch")
        snippet = patch if patch else "[binary or patch omitted]"
        part = (
            f"File: {item.get('filename', 'unknown')}\n"
            f"Status: {item.get('status', 'modified')}\n"
            f"Additions: {item.get('additions', 0)}\n"
            f"Deletions: {item.get('deletions', 0)}\n"
            f"Changes: {item.get('changes', 0)}\n"
            f"Patch:\n{snippet}\n"
        )
        if total_length + len(part) > settings.github_diff_max_chars:
            remaining = settings.github_diff_max_chars - total_length
            if remaining <= 0:
                break
            parts.append(part[:remaining] + "\n[truncated]\n")
            break
        parts.append(part)
        total_length += len(part)
    return "\n---\n".join(parts)


def serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
