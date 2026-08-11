from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": settings.MOCK_MODE,
        "environment": settings.ENVIRONMENT,
    }
