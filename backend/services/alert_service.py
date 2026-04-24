import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


def _format_generic(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _format_slack(payload: dict[str, Any]) -> dict[str, Any]:
    alert = payload.get("alert") or {}
    manual_handoff = payload.get("manual_handoff") or {}
    text = (
        f"PR Agent Alert\n"
        f"Repo: {payload.get('repo')}\n"
        f"PR: #{payload.get('pr_number')} {payload.get('title')}\n"
        f"Status: {payload.get('status')}\n"
        f"Summary: {alert.get('summary') or payload.get('error_message') or 'N/A'}"
    )
    fields = [
        {"type": "mrkdwn", "text": f"*Repo*\n{payload.get('repo')}"},
        {"type": "mrkdwn", "text": f"*PR*\n#{payload.get('pr_number')}"},
        {"type": "mrkdwn", "text": f"*Status*\n{payload.get('status')}"},
        {"type": "mrkdwn", "text": f"*Severity*\n{manual_handoff.get('severity') or 'unknown'}"},
    ]
    actions = manual_handoff.get("recommended_actions") or []
    if actions:
        text += "\nActions:\n- " + "\n- ".join(str(item) for item in actions[:3])
    return {"text": text, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}, {"type": "section", "fields": fields}]}


def _format_feishu(payload: dict[str, Any]) -> dict[str, Any]:
    alert = payload.get("alert") or {}
    manual_handoff = payload.get("manual_handoff") or {}
    actions = manual_handoff.get("recommended_actions") or []
    action_lines = "\n".join(f"• {item}" for item in actions[:3]) or "• 无"
    summary = alert.get("summary") or payload.get("error_message") or "N/A"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "PR Agent 告警"},
                "template": "orange",
            },
            "elements": [
                {"tag": "markdown", "content": f"**Repo**: {payload.get('repo')}\n**PR**: #{payload.get('pr_number')} {payload.get('title')}"},
                {"tag": "markdown", "content": f"**状态**: {payload.get('status')}\n**级别**: {manual_handoff.get('severity') or 'unknown'}"},
                {"tag": "markdown", "content": f"**摘要**: {summary}"},
                {"tag": "markdown", "content": f"**建议动作**:\n{action_lines}"},
            ],
        },
    }


def _format_alert_payload(payload: dict[str, Any]) -> dict[str, Any]:
    provider = settings.pr_alert_provider.strip().lower() or "generic"
    if provider == "slack":
        return _format_slack(payload)
    if provider == "feishu":
        return _format_feishu(payload)
    return _format_generic(payload)


async def send_pr_alert(payload: dict[str, Any]) -> bool:
    webhook_url = settings.pr_alert_webhook_url.strip()
    if not webhook_url:
        logger.info("PR alert skipped: webhook not configured")
        return False
    try:
        formatted_payload = _format_alert_payload(payload)
        async with httpx.AsyncClient(timeout=settings.pr_alert_timeout) as client:
            response = await client.post(webhook_url, json=formatted_payload)
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("PR alert dispatch failed")
        return False
