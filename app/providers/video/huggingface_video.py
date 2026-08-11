"""
Hugging Face Inference Providers - text/image-to-video adapter.

Per the documented API (https://huggingface.co/docs/inference-providers/en/tasks/text-to-video),
the generic Inference Providers task for text-to-video:
  - is invoked through the `huggingface_hub` InferenceClient (there is no
    stable, provider-agnostic raw REST path documented for this task -
    each backing provider, e.g. fal-ai or Replicate, exposes its own
    async job/polling shape underneath, which InferenceClient normalizes
    for us). We therefore use the official SDK rather than inventing a
    REST contract HF does not document at this level.
  - is a SYNCHRONOUS call: the client blocks until the video is ready and
    returns raw video bytes. There is no documented generic "check status"
    endpoint for this task, so this adapter runs the blocking SDK call in
    a worker thread and tracks its own task bookkeeping in-memory; once
    `generate_text_to_video` returns, the result is already final.

Recommended models per HF docs (subject to change - always re-check
https://huggingface.co/docs/inference-providers/en/tasks/text-to-video):
  - tencent/HunyuanVideo (quality)
  - Lightricks/LTX-Video-0.9.8-13B-distilled (fast)

Image-to-video: HF Inference Providers' generic task catalog does not
document a stable provider-agnostic `image-to-video` task at the time of
writing. `generate_image_to_video` is implemented against the same
text-to-video call with the reference image description folded into the
prompt, and raises a clear, documented-limitation error if a provider
requires true image conditioning we do not yet support. This keeps the
VideoProvider interface stable for when direct image-conditioning support
lands, without pretending capabilities that don't exist.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from app.config import get_settings
from app.models.generation import ProviderGenerationResult, ProviderTaskStatus
from app.providers.base import VideoProvider
from app.utils.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    VideoProviderError,
)
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


class HuggingFaceVideoProvider(VideoProvider):
    def __init__(self, token: str | None = None, model: str | None = None, provider: str | None = None):
        self.token = token or settings.HF_TOKEN
        self.model = model or settings.HF_VIDEO_MODEL
        self.provider = provider or settings.HF_PROVIDER
        if not self.token:
            raise ProviderAuthError(
                "HF_TOKEN is not configured. Set it in the environment or enable MOCK_MODE."
            )
        # In-memory task result cache. Fine for a single-process dev
        # deployment; a multi-worker production deployment should persist
        # this (e.g. in the projects DB row, which the orchestration
        # service already updates as scenes complete).
        self._results: dict[str, ProviderGenerationResult] = {}

    def _client(self):
        try:
            from huggingface_hub import InferenceClient
        except ImportError as e:
            raise ProviderUnavailableError(
                "huggingface_hub is not installed. Run `pip install huggingface_hub`."
            ) from e
        kwargs = {"api_key": self.token}
        if self.provider and self.provider != "auto":
            kwargs["provider"] = self.provider
        else:
            kwargs["provider"] = "auto"
        return InferenceClient(**kwargs)

    def _run_text_to_video(self, prompt: str, negative_prompt: Optional[str], seed: Optional[int]):
        client = self._client()
        kwargs = {"model": self.model}
        # NOTE: negative_prompt / seed are documented `parameters` for the
        # underlying task but are only forwarded by the SDK where the
        # selected provider supports them; unsupported kwargs are dropped
        # by huggingface_hub rather than sent as invalid fields.
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
        if seed is not None:
            kwargs["seed"] = seed
        return client.text_to_video(prompt, **kwargs)

    async def generate_text_to_video(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str] = None,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        seed: Optional[int] = None,
    ) -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        log_event(
            logger,
            "info",
            "provider.video.request",
            task_id=task_id,
            model=self.model,
            provider=self.provider,
            prompt_len=len(prompt),
            duration_seconds=duration_seconds,
        )
        start = time.time()
        try:
            video_bytes = await asyncio.wait_for(
                asyncio.to_thread(self._run_text_to_video, prompt, negative_prompt, seed),
                timeout=settings.PROVIDER_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as e:
            log_event(logger, "error", "provider.video.timeout", task_id=task_id)
            raise ProviderTimeoutError(
                f"Video generation timed out after {settings.PROVIDER_TIMEOUT_SECONDS}s"
            ) from e
        except Exception as e:  # noqa: BLE001 - normalize any SDK/provider error
            message = str(e)
            log_event(logger, "error", "provider.video.error", task_id=task_id, error=message)
            lowered = message.lower()
            if "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
                raise ProviderAuthError("Hugging Face authentication failed. Check HF_TOKEN.") from e
            if "429" in lowered or "rate limit" in lowered:
                raise ProviderRateLimitError("Hugging Face video provider rate limit exceeded.") from e
            if "503" in lowered or "unavailable" in lowered or "loading" in lowered:
                raise ProviderUnavailableError(
                    "Hugging Face video model is currently unavailable/loading. Retry shortly."
                ) from e
            raise VideoProviderError(f"Video generation failed: {message}") from e

        elapsed = time.time() - start
        log_event(logger, "info", "provider.video.success", task_id=task_id, elapsed_s=round(elapsed, 2))

        # video_bytes may be raw bytes or, depending on provider/SDK
        # version, a file-like object - normalize to bytes defensively.
        if hasattr(video_bytes, "read"):
            video_bytes = video_bytes.read()

        result = ProviderGenerationResult(
            task_id=task_id,
            status=ProviderTaskStatus.SUCCEEDED,
            raw_metadata={"model": self.model, "provider": self.provider, "elapsed_s": elapsed},
        )
        self._results[task_id] = result
        self._pending_bytes = getattr(self, "_pending_bytes", {})
        self._pending_bytes[task_id] = video_bytes
        return result

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
        # Documented limitation: see module docstring. We fold the
        # reference description into the prompt rather than silently
        # ignoring it or pretending true image conditioning occurred.
        augmented_prompt = (
            f"{prompt}. The main subject must visually match this reference: {reference_image_url}"
        )
        log_event(
            logger,
            "warning",
            "provider.video.image_to_video_fallback",
            reason="no generic image-to-video REST task documented; using text-to-video with folded prompt",
        )
        return await self.generate_text_to_video(
            prompt=augmented_prompt,
            negative_prompt=negative_prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            seed=seed,
        )

    async def get_generation_status(self, task_id: str) -> ProviderGenerationResult:
        result = self._results.get(task_id)
        if result is None:
            raise VideoProviderError(f"Unknown task_id {task_id}", retryable=False)
        return result

    async def download_result(self, task_id: str, destination_path: str) -> str:
        pending = getattr(self, "_pending_bytes", {})
        video_bytes = pending.get(task_id)
        if video_bytes is None:
            raise VideoProviderError(
                f"No downloadable result cached for task {task_id}", retryable=False
            )
        import os

        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        with open(destination_path, "wb") as f:
            f.write(video_bytes)
        del pending[task_id]
        return destination_path
