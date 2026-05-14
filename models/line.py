from typing import Any

from pydantic import BaseModel, Field


class LineWebhookEvent(BaseModel):
    type: str
    replyToken: str | None = None
    message: dict[str, Any] | None = None



class LineWebhookPayload(BaseModel):
    events: list[LineWebhookEvent] = Field(default_factory=list)

