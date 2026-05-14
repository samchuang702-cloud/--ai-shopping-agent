import json
from typing import Any

from fastapi import APIRouter, Request

from models.line import LineWebhookPayload
from models.shopping import ShoppingRequest
from services.line_service import reply_to_line, verify_line_signature
from services.recommendation_service import run_agent


router = APIRouter()


@router.post("/line/webhook")
async def line_webhook(request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    verify_line_signature(raw_body, request.headers.get("x-line-signature"))
    payload = LineWebhookPayload.model_validate(json.loads(raw_body or b"{}"))
    replies = []
    delivery_results = []

    for event in payload.events:
        if event.type != "message":
            continue
        text = ""
        if event.message and event.message.get("type") == "text":
            text = str(event.message.get("text", "")).strip()
        if not text:
            continue

        result = run_agent(ShoppingRequest(query=text))
        messages = [
            {
                "type": "text",
                "text": (
                    f"我判斷你的需求是：{result.analysis.problem}\n"
                    f"推薦方向：{result.decision.selected_solution.method}"
                ),
            },
            result.line_flex_message,
        ]
        replies.append({"replyToken": event.replyToken, "messages": messages})
        delivery_results.append(reply_to_line(event.replyToken, messages))

    return {
        "status": "ok",
        "mode": "reply_api",
        "note": "如果 replyToken 是本機 dummy，系統會略過實際 LINE 回覆。",
        "reply_messages": replies,
        "delivery_results": delivery_results,
    }
