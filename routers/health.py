import os

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, bool | str]:
    return {
        "status": "ok",
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
    }
