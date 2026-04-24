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


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


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
            headers=_github_headers(token),
        )
    response.raise_for_status()
    return response.json()


async def fetch_pull_request(repo: GitHubRepository, pr_number: int) -> dict[str, Any]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/pulls/{pr_number}",
            headers=_github_headers(token),
        )
    response.raise_for_status()
    return response.json()


async def fetch_pull_requests(repo: GitHubRepository, *, state: str = "open", per_page: int = 10) -> list[dict[str, Any]]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/pulls",
            headers=_github_headers(token),
            params={"state": state, "per_page": per_page},
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
                headers=_github_headers(token),
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


async def fetch_pull_request_commits(repo: GitHubRepository, pr_number: int, per_page: int = 10) -> list[dict[str, Any]]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/pulls/{pr_number}/commits",
            headers=_github_headers(token),
            params={"per_page": per_page},
        )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


async def fetch_commit_check_runs(repo: GitHubRepository, ref: str) -> list[dict[str, Any]]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/commits/{ref}/check-runs",
            headers={**_github_headers(token), "Accept": "application/vnd.github+json, application/vnd.github.antiope-preview+json"},
        )
    response.raise_for_status()
    data = response.json()
    check_runs = data.get("check_runs")
    return check_runs if isinstance(check_runs, list) else []


async def fetch_issue(repo: GitHubRepository, issue_number: int) -> dict[str, Any]:
    token = decrypt_github_token(repo.github_token_encrypted)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/repos/{repo.repo_owner}/{repo.repo_name}/issues/{issue_number}",
            headers=_github_headers(token),
        )
    response.raise_for_status()
    return response.json()


async def search_repository_code(repo: GitHubRepository, query: str, per_page: int = 5) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    token = decrypt_github_token(repo.github_token_encrypted)
    scoped_query = f"{query} repo:{repo.repo_owner}/{repo.repo_name}"
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            f"{settings.github_api_base_url}/search/code",
            headers=_github_headers(token),
            params={"q": scoped_query, "per_page": per_page},
        )
    response.raise_for_status()
    data = response.json()
    items = data.get("items")
    return items if isinstance(items, list) else []


def build_reviewable_diff(files: list[dict[str, Any]]) -> str:
    ranked_files = sorted(files[: settings.github_diff_max_files], key=_review_file_priority, reverse=True)
    parts: list[str] = []
    total_length = 0
    for item in ranked_files:
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


def _review_file_priority(item: dict[str, Any]) -> tuple[int, int, int]:
    filename = str(item.get("filename") or "").lower()
    status = str(item.get("status") or "modified").lower()
    changes = int(item.get("changes") or 0)
    additions = int(item.get("additions") or 0)

    risk = 0
    if any(token in filename for token in ["auth", "security", "permission", "admin", "payment", "order", "transaction"]):
        risk += 7
    if any(token in filename for token in ["service", "controller", "handler", "api", "router"]):
        risk += 5
    if any(token in filename for token in ["config", ".yml", ".yaml", ".json", ".toml", ".ini"]):
        risk += 4
    if any(token in filename for token in ["test", "spec"]):
        risk -= 2
    if status in {"added", "renamed"}:
        risk += 2
    if status == "removed":
        risk += 3
    return (risk, changes, additions)


def serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
