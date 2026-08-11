from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import LLMProvider
from app.providers.llm.mock_llm import MockLLMProvider
from app.providers.llm.huggingface_llm import HuggingFaceLLMProvider

settings = get_settings()


@lru_cache
def get_llm_provider() -> LLMProvider:
    if settings.MOCK_MODE:
        return MockLLMProvider()
    return HuggingFaceLLMProvider()
