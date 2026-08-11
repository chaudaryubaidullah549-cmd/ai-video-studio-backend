from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import MusicProvider, SoundEffectProvider
from app.providers.music.mock_music import MockMusicProvider, MockSoundEffectProvider
from app.providers.music.huggingface_music import HuggingFaceMusicProvider, HuggingFaceSoundEffectProvider

settings = get_settings()


@lru_cache
def get_music_provider() -> MusicProvider:
    # Music generation has no documented free Inference Providers task
    # yet (see huggingface_music.py) - default to the procedural provider
    # unless MOCK_MODE is explicitly disabled AND the operator has wired
    # up a real backend by editing this factory.
    if settings.MOCK_MODE:
        return MockMusicProvider()
    return MockMusicProvider()  # documented fallback, see module docstring


@lru_cache
def get_sfx_provider() -> SoundEffectProvider:
    if settings.MOCK_MODE:
        return MockSoundEffectProvider()
    return MockSoundEffectProvider()
