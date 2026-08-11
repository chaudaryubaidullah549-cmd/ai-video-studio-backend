from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import VideoProvider
from app.providers.video.mock_video import MockVideoProvider
from app.providers.video.huggingface_video import HuggingFaceVideoProvider

settings = get_settings()


@lru_cache
def get_video_provider() -> VideoProvider:
    if settings.MOCK_MODE:
        return MockVideoProvider()
    return HuggingFaceVideoProvider()
