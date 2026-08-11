"""
Mock video provider used when MOCK_MODE=true.

Generates a small, real, playable MP4 for every "clip" using FFmpeg's
lavfi test sources (color bars / gradient + a burned-in caption showing
the prompt), so the rest of the pipeline (assembly, muxing, download
endpoint) can be exercised end-to-end without any paid API calls.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
import uuid
from typing import Optional

from app.config import get_settings
from app.models.generation import ProviderGenerationResult, ProviderTaskStatus
from app.providers.base import VideoProvider
from app.utils.errors import VideoProviderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()

_ASPECT_TO_SIZE = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (960, 960),
}


def _safe_caption(text: str, limit: int = 60) -> str:
    cleaned = text.replace("'", "").replace(":", "-").replace("\n", " ")
    return cleaned[:limit]


class MockVideoProvider(VideoProvider):
    def __init__(self):
        self._results: dict[str, ProviderGenerationResult] = {}
        self._paths: dict[str, str] = {}

    def _synthesize(self, task_id: str, prompt: str, duration: float, aspect_ratio: str) -> str:
        width, height = _ASPECT_TO_SIZE.get(aspect_ratio, (1280, 720))
        temp_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"mock_clip_{task_id}.mp4")
        caption = _safe_caption(prompt)
        # A moving gradient (so it's visibly "video", not a static frame)
        # with the scene prompt burned in as text - deterministic, fast,
        # and needs no external network access.
        filter_complex = (
            f"drawtext=text='{caption}':fontcolor=white:fontsize=28:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=10"
        )
        cmd = [
            settings.FFMPEG_BINARY,
            "-y",
            "-f", "lavfi",
            "-i", f"testsrc2=s={width}x{height}:d={max(duration, 1)}:rate=24",
            "-vf", filter_complex,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(max(duration, 1)),
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = getattr(e, "stderr", b"")
            stderr_text = stderr.decode(errors="ignore") if isinstance(stderr, bytes) else str(stderr)
            log_event(logger, "error", "mock_video.ffmpeg_error", error=stderr_text[:500])
            raise VideoProviderError(f"Mock video synthesis failed: {stderr_text[:300]}") from e
        return out_path

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
        log_event(logger, "info", "mock_video.generate", task_id=task_id, prompt_len=len(prompt))
        # Simulate realistic-ish latency without actually being slow.
        await asyncio.sleep(0.2)
        path = await asyncio.to_thread(self._synthesize, task_id, prompt, duration_seconds, aspect_ratio)
        result = ProviderGenerationResult(
            task_id=task_id,
            status=ProviderTaskStatus.SUCCEEDED,
            output_local_path=path,
            raw_metadata={"mock": True, "prompt": prompt[:200]},
        )
        self._results[task_id] = result
        self._paths[task_id] = path
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
        return await self.generate_text_to_video(
            prompt=f"{prompt} [ref: {reference_image_url}]",
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
        src = self._paths.get(task_id)
        if src is None or not os.path.exists(src):
            raise VideoProviderError(f"No cached mock result for task {task_id}", retryable=False)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(destination_path):
            with open(src, "rb") as f_in, open(destination_path, "wb") as f_out:
                f_out.write(f_in.read())
        return destination_path
