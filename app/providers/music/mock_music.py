"""
Procedural music/SFX provider.

Used for MOCK_MODE=true and as the practical default for music/SFX even
outside mock mode, since no free-tier HF Inference Providers task covers
music generation yet (see huggingface_music.py). Generates mood-appropriate
tonal beds via FFmpeg so the render pipeline has real audio to mix - not
meant to sound "produced", just to make the end-to-end pipeline real.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid

from app.config import get_settings
from app.models.enums import AudioMood
from app.models.generation import ProviderGenerationResult, ProviderTaskStatus
from app.providers.base import MusicProvider, SoundEffectProvider
from app.utils.errors import MusicProviderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()

_MOOD_PROFILE = {
    AudioMood.ENERGETIC: {"freq": 220, "tempo_hz": 4.0},
    AudioMood.EMOTIONAL: {"freq": 196, "tempo_hz": 0.5},
    AudioMood.SUSPENSE: {"freq": 110, "tempo_hz": 0.2},
    AudioMood.PEACEFUL: {"freq": 261, "tempo_hz": 0.3},
    AudioMood.NEUTRAL: {"freq": 200, "tempo_hz": 1.0},
    AudioMood.TRIUMPHANT: {"freq": 330, "tempo_hz": 2.0},
    AudioMood.OMINOUS: {"freq": 80, "tempo_hz": 0.15},
}


class MockMusicProvider(MusicProvider):
    def __init__(self):
        self._paths: dict[str, str] = {}

    def _synth(self, task_id: str, mood: str, duration: float) -> str:
        try:
            mood_enum = AudioMood(mood)
        except ValueError:
            mood_enum = AudioMood.NEUTRAL
        profile = _MOOD_PROFILE[mood_enum]
        temp_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"mock_music_{task_id}.wav")
        # Two detuned sine layers with tremolo, mood-driven frequency/tempo,
        # gives a distinguishable ambient bed per mood.
        cmd = [
            settings.FFMPEG_BINARY,
            "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={profile['freq']}:duration={max(duration, 1)}",
            "-f", "lavfi",
            "-i", f"sine=frequency={profile['freq'] * 1.5}:duration={max(duration, 1)}",
            "-filter_complex",
            f"[0]tremolo=f={profile['tempo_hz']}:d=0.5[a];[1]volume=0.3[b];[a][b]amix=inputs=2:duration=longest,volume=0.2",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise MusicProviderError(f"Mock music synthesis failed: {e}") from e
        return out_path

    async def generate_music(self, *, mood: str, duration_seconds: float, style: str = "cinematic") -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        log_event(logger, "info", "mock_music.generate", mood=mood, duration=duration_seconds)
        path = await asyncio.to_thread(self._synth, task_id, mood, duration_seconds)
        self._paths[task_id] = path
        return ProviderGenerationResult(task_id=task_id, status=ProviderTaskStatus.SUCCEEDED, output_local_path=path)

    async def download_result(self, task_id: str, destination_path: str) -> str:
        src = self._paths.get(task_id)
        if src is None or not os.path.exists(src):
            raise MusicProviderError(f"No cached mock music for task {task_id}", retryable=False)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(destination_path):
            with open(src, "rb") as f_in, open(destination_path, "wb") as f_out:
                f_out.write(f_in.read())
        return destination_path


class MockSoundEffectProvider(SoundEffectProvider):
    def __init__(self):
        self._paths: dict[str, str] = {}

    def _synth(self, task_id: str, duration: float) -> str:
        temp_dir = os.path.join(settings.LOCAL_STORAGE_PATH, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        out_path = os.path.join(temp_dir, f"mock_sfx_{task_id}.wav")
        cmd = [
            settings.FFMPEG_BINARY,
            "-y",
            "-f", "lavfi",
            "-i", f"anoisesrc=d={max(duration, 0.3)}:c=pink:a=0.2",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=20)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise MusicProviderError(f"Mock SFX synthesis failed: {e}") from e
        return out_path

    async def generate_sfx(self, *, description: str, duration_seconds: float) -> ProviderGenerationResult:
        task_id = str(uuid.uuid4())
        log_event(logger, "info", "mock_sfx.generate", description=description[:80])
        path = await asyncio.to_thread(self._synth, task_id, duration_seconds)
        self._paths[task_id] = path
        return ProviderGenerationResult(task_id=task_id, status=ProviderTaskStatus.SUCCEEDED, output_local_path=path)

    async def download_result(self, task_id: str, destination_path: str) -> str:
        src = self._paths.get(task_id)
        if src is None or not os.path.exists(src):
            raise MusicProviderError(f"No cached mock SFX for task {task_id}", retryable=False)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(destination_path):
            with open(src, "rb") as f_in, open(destination_path, "wb") as f_out:
                f_out.write(f_in.read())
        return destination_path
