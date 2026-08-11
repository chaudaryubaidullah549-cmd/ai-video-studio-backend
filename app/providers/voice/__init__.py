from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import VoiceProvider
from app.providers.voice.mock_voice import MockVoiceProvider
from app.providers.voice.huggingface_voice import HuggingFaceVoiceProvider

settings = get_settings()


@lru_cache
def get_voice_provider() -> VoiceProvider:
    if settings.MOCK_MODE:
        return MockVoiceProvider()
    return HuggingFaceVoiceProvider()
