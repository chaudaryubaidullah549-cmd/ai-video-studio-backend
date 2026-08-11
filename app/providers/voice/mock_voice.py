"""
Mock voice provider (MOCK_MODE=true).

Synthesizes a short tone/silence placeholder audio clip via FFmpeg for
every line of dialogue/narration, roughly sized to the text length, so
the render pipeline can mix real audio tracks end-to-end.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from typing import Any

from app.config import get_settings
from app.models.generation import ProviderGenerationResult, ProviderTaskStatus
from app.providers.base import VoiceProvider
from app.utils.errors import VoiceProviderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


def _estimate_duration(text: str) -> float:
    words = max(len(text.split()), 1)
    # ~2.5 words/sec average speaking pace, clamp to sane bounds.
    return max(1.0, min(20.0, words / 2.5))


class MockVoiceProvider(VoiceProvider):
    def __init__(self):
        self._paths: dict[str, str] = {}
        self._results: dict[str, ProviderGenerationResult] = {}

    def _synthesize(self, task_id: str, text: str, freq: int = 220) -> str:
        duration = _estimate_duration(text)
        temp_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"mock_voice_{task_id}.wav")
        cmd = [
            settings.FFMPEG_BINARY,
            "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={duration}",
            "-af", "volume=0.15",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise VoiceProviderError(f"Mock voice synthesis failed: {e}") from e
        return out_path

    async def generate_speech(self, *, text: str, voice: str = "auto", language: str = "en") -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        log_event(logger, "info", "mock_voice.generate_speech", text_len=len(text))
        path = await asyncio.to_thread(self._synthesize, task_id, text, 220)
        result = ProviderGenerationResult(task_id=task_id, status=ProviderTaskStatus.SUCCEEDED, output_local_path=path)
        self._paths[task_id] = path
        self._results[task_id] = result
        return result

    async def generate_dialogue(
        self,
        *,
        character_name: str,
        text: str,
        voice_characteristics: dict[str, Any],
        language: str = "en",
    ) -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        # Vary tone slightly per character so mock dialogue tracks are at
        # least distinguishable in a waveform view.
        freq = 180 + (abs(hash(character_name)) % 120)
        log_event(logger, "info", "mock_voice.generate_dialogue", character=character_name, text_len=len(text))
        path = await asyncio.to_thread(self._synthesize, task_id, text, freq)
        result = ProviderGenerationResult(task_id=task_id, status=ProviderTaskStatus.SUCCEEDED, output_local_path=path)
        self._paths[task_id] = path
        self._results[task_id] = result
        return result

    async def download_result(self, task_id: str, destination_path: str) -> str:
        src = self._paths.get(task_id)
        if src is None or not os.path.exists(src):
            raise VoiceProviderError(f"No cached mock voice result for task {task_id}", retryable=False)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(destination_path):
            with open(src, "rb") as f_in, open(destination_path, "wb") as f_out:
                f_out.write(f_in.read())
        return destination_path
