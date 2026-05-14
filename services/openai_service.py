import json
import os
from typing import Any

from fastapi import HTTPException
from openai import OpenAI, OpenAIError


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set. Create a .env file and add your API key.",
        )
    return OpenAI(api_key=api_key)



def parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "The AI response was not valid JSON.", "raw_response": content},
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="The AI response JSON must be an object.")
    return parsed



def llm_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI request failed: {exc.__class__.__name__}",
        ) from exc

    return parse_json_object(response.choices[0].message.content or "{}")

