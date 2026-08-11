"""
Provider interfaces.

Every external AI capability (LLM, video, voice, music, storage) is
accessed through one of these abstract interfaces. This is what lets the
video model, voice model, etc. be swapped later without touching
services/ or api/ code: a new provider is just a new subclass registered
in the corresponding providers/<kind>/__init__.py factory.

Concrete implementations live in providers/<kind>/*.py:
  - providers/video/huggingface_video.py  (real, HF Inference Providers)
  - providers/video/mock_video.py         (MOCK_MODE)
  - ... same pattern for llm/voice/music/storage
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.models.generation import ProviderGenerationResult


class LLMProvider(ABC):
    """Text generation for story planning, character extraction, scene
    breakdown, and prompt assembly. Implementations must return valid
    JSON when `json_mode=True` is passed - callers rely on this to parse
    structured output directly.
    """

    @abstractmethod
    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        max_tokens: int = 2000,
        temperature: float = 0.8,
    ) -> str:
        """Return the raw text (or JSON string) completion."""
        raise NotImplementedError


class VideoProvider(ABC):
    """Text/image-to-video generation.

    IMPORTANT - character consistency: text- and even image-conditioned
    open video models do NOT guarantee pixel-identical characters across
    independent clips. This interface is deliberately shaped so an image
    reference (e.g. a generated character portrait) CAN be passed into
    `generate_image_to_video` once a reference-image pipeline is wired up,
    which materially improves - but never guarantees - consistency. Do
    not represent generation results to users as perfectly consistent.
    """

    @abstractmethod
    async def generate_text_to_video(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str] = None,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
    ) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def generate_image_to_video(
        self,
        *,
        prompt: str,
        reference_image_url: str,
        negative_prompt: Optional[str] = None,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
    ) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def get_generation_status(self, task_id: str) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def download_result(self, task_id: str, destination_path: str) -> str:
        """Download the finished asset to `destination_path`. Returns the
        local path actually written."""
        raise NotImplementedError


class VoiceProvider(ABC):
    @abstractmethod
    async def generate_speech(
        self,
        *,
        text: str,
        voice: str = "auto",
        language: str = "en",
    ) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def generate_dialogue(
        self,
        *,
        character_name: str,
        text: str,
        voice_characteristics: dict[str, Any],
        language: str = "en",
    ) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def download_result(self, task_id: str, destination_path: str) -> str:
        raise NotImplementedError


class MusicProvider(ABC):
    @abstractmethod
    async def generate_music(
        self,
        *,
        mood: str,
        duration_seconds: float,
        style: str = "cinematic",
    ) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def download_result(self, task_id: str, destination_path: str) -> str:
        raise NotImplementedError


class SoundEffectProvider(ABC):
    @abstractmethod
    async def generate_sfx(self, *, description: str, duration_seconds: float) -> ProviderGenerationResult:
        raise NotImplementedError

    @abstractmethod
    async def download_result(self, task_id: str, destination_path: str) -> str:
        raise NotImplementedError


class StorageProvider(ABC):
    """Abstraction over where generated artifacts and metadata live.

    `local` (development) writes to disk under LOCAL_STORAGE_PATH and
    serves it via a static route. Swapping to S3/GCS later means adding a
    new StorageProvider implementation - no service code changes.
    """

    @abstractmethod
    def save_file(self, *, relative_path: str, content: bytes) -> str:
        """Persist bytes, return a publicly resolvable URL."""
        raise NotImplementedError

    @abstractmethod
    def save_file_from_path(self, *, relative_path: str, source_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def url_for(self, relative_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def local_path_for_url(self, url: str) -> str:
        """Resolve a previously-issued URL back to a local filesystem path
        that FFmpeg can read. For remote backends (S3 etc.) an
        implementation would download to a temp file and return that path."""
        raise NotImplementedError
