import base64
import hashlib
import hmac
import os
from typing import Any

import httpx
from fastapi import HTTPException


LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


def verify_line_signature(body: bytes, signature: str | None) -> None:
    if os.getenv("LINE_VERIFY_SIGNATURE", "false").lower() != "true":
        return

    channel_secret = os.getenv("LINE_CHANNEL_SECRET")
    if not channel_secret or not signature:
        return

    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="LINE 簽章驗證失敗。")



def reply_to_line(reply_token: str | None, messages: list[dict[str, Any]]) -> dict[str, Any]:
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        return {"sent": False, "reason": "LINE_CHANNEL_ACCESS_TOKEN 未設定。"}
    if not reply_token:
        return {"sent": False, "reason": "沒有 replyToken。"}
    if reply_token.startswith("dummy"):
        return {"sent": False, "reason": "本機 dummy replyToken，略過 LINE Reply API。"}

    response = httpx.post(
        LINE_REPLY_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"replyToken": reply_token, "messages": messages},
        timeout=10,
    )
    if response.status_code >= 400:
        return {
            "sent": False,
            "status_code": response.status_code,
            "reason": response.text[:500],
        }
    return {"sent": True, "status_code": response.status_code}

