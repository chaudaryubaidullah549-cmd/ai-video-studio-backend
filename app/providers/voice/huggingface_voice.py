"""
Hugging Face Inference Providers - text-to-speech adapter.

Per the documented text-to-speech task
(https://huggingface.co/docs/inference-providers/en/tasks/text-to-speech),
the request/response shape mirrors text-to-video: send `inputs` (the
text) and receive raw audio bytes back. We use the same official SDK
(`huggingface_hub.InferenceClient.text_to_speech`) rather than hand-
rolling a REST call, since - as with video - provider-specific job
handling is normalized by the SDK and not documented as a stable raw
REST contract at the generic task level.

HF_TTS_MODEL is optional: if unset, InferenceClient selects a recommended
default model for the task. Voice *characteristics* (pitch/tone/pace) and
per-character voice consistency are best-effort: most open TTS models
accept a single "voice"/speaker id rather than free-form characteristic
tuning, so `generate_dialogue` embeds character voice notes into logs for
traceability but cannot guarantee the model actually renders them.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from app.config import get_settings
from app.models.generation import ProviderGenerationResult, ProviderTaskStatus
from app.providers.base import VoiceProvider
from app.utils.errors import (
    ProviderAuthError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    VoiceProviderError,
)
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


class HuggingFaceVoiceProvider(VoiceProvider):
    def __init__(self, token: str | None = None, model: str | None = None):
        self.token = token or settings.HF_TOKEN
        self.model = model or settings.HF_TTS_MODEL or None
        if not self.token:
            raise ProviderAuthError(
                "HF_TOKEN is not configured. Set it in the environment or enable MOCK_MODE."
            )
        self._pending: dict[str, bytes] = {}
        self._results: dict[str, ProviderGenerationResult] = {}

    def _client(self):
        try:
            from huggingface_hub import InferenceClient
        except ImportError as e:
            raise ProviderUnavailableError(
                "huggingface_hub is not installed. Run `pip install huggingface_hub`."
            ) from e
        return InferenceClient(api_key=self.token, provider="auto")

    def _run_tts(self, text: str) -> bytes:
        client = self._client()
        kwargs: dict[str, Any] = {}
        if self.model:
            kwargs["model"] = self.model
        audio = client.text_to_speech(text, **kwargs)
        if hasattr(audio, "read"):
            audio = audio.read()
        return audio

    async def _synthesize(self, text: str) -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        try:
            audio_bytes = await asyncio.wait_for(
                asyncio.to_thread(self._run_tts, text),
                timeout=settings.PROVIDER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as e:
            raise ProviderTimeoutError("Hugging Face TTS request timed out") from e
        except Exception as e:  # noqa: BLE001
            message = str(e)
            lowered = message.lower()
            if "401" in lowered or "unauthorized" in lowered:
                raise ProviderAuthError("Hugging Face authentication failed. Check HF_TOKEN.") from e
            raise VoiceProviderError(f"Voice generation failed: {message}") from e

        self._pending[task_id] = audio_bytes
        result = ProviderGenerationResult(
            task_id=task_id,
            status=ProviderTaskStatus.SUCCEEDED,
            raw_metadata={"model": self.model or "provider-default"},
        )
        self._results[task_id] = result
        return result

    async def generate_speech(self, *, text: str, voice: str = "auto", language: str = "en") -> ProviderGenerationResult:
        log_event(logger, "info", "provider.voice.request", text_len=len(text), language=language)
        return await self._synthesize(text)

    async def generate_dialogue(
        self,
        *,
        character_name: str,
        text: str,
        voice_characteristics: dict[str, Any],
        language: str = "en",
    ) -> ProviderGenerationResult:
        log_event(
            logger,
            "info",
            "provider.voice.dialogue_request",
            character=character_name,
            text_len=len(text),
            characteristics=voice_characteristics,
        )
        return await self._synthesize(text)

    async def download_result(self, task_id: str, destination_path: str) -> str:
        data = self._pending.get(task_id)
        if data is None:
            raise VoiceProviderError(f"No cached voice result for task {task_id}", retryable=False)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, "wb") as f:
            f.write(data)
        del self._pending[task_id]
        return destination_path
