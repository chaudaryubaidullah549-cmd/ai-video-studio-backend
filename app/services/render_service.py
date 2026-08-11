"""Render service: assembles per-scene clips + audio into the final MP4.

Pipeline (per spec):
  scene clips + voice + music + sfx -> audio mixing -> transitions -> final MP4

Output: H.264 video, AAC audio, yuv420p, web-compatible MP4 (faststart).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.config import get_settings
from app.models.project import Project
from app.providers.base import StorageProvider
from app.utils import ffmpeg as ff
from app.utils.errors import RenderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


class RenderService:
    def __init__(self, storage: StorageProvider):
        self.storage = storage

    async def render_project(self, project: Project) -> str:
        completed_scenes = [s for s in project.scenes if s.media.video_url]
        if not completed_scenes:
            raise RenderError("No completed scenes with video available to render")

        work_dir = Path(settings.LOCAL_STORAGE_PATH) / "temp" / f"render_{project.id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        normalized_clips: list[str] = []
        for scene in sorted(completed_scenes, key=lambda s: s.index):
            src = self.storage.local_path_for_url(scene.media.video_url)

            # Build this scene's mixed audio (voice + ducked music + sfx),
            # then mux it onto the normalized video clip so concatenation
            # carries audio through per-scene.
            voice_paths = [self.storage.local_path_for_url(u) for u in scene.media.voice_track_urls]
            music_path = self.storage.local_path_for_url(scene.media.music_url) if scene.media.music_url else None
            sfx_paths = [self.storage.local_path_for_url(u) for u in scene.media.sfx_urls]

            norm_video = str(work_dir / f"scene_{scene.index:03d}_video.mp4")
            await asyncio.to_thread(
                ff.normalize_clip, src, norm_video, project.settings.aspect_ratio.value, scene.duration
            )

            mixed_audio = None
            if voice_paths or music_path or sfx_paths:
                mixed_audio_path = str(work_dir / f"scene_{scene.index:03d}_audio.aac")
                mixed_audio = await asyncio.to_thread(
                    ff.mix_audio_tracks,
                    voice_paths=voice_paths,
                    music_path=music_path,
                    sfx_paths=sfx_paths,
                    duration=scene.duration,
                    dst_path=mixed_audio_path,
                )

            scene_final = str(work_dir / f"scene_{scene.index:03d}_final.mp4")
            await asyncio.to_thread(ff.mux_video_audio, norm_video, mixed_audio, scene_final)
            normalized_clips.append(scene_final)

        concatenated = str(work_dir / "concatenated.mp4")
        await asyncio.to_thread(ff.concat_clips, normalized_clips, concatenated)

        relative_final = f"projects/{project.id}/final.mp4"
        final_url = self.storage.save_file_from_path(relative_path=relative_final, source_path=concatenated)

        log_event(logger, "info", "render.project.success", project_id=project.id, scenes=len(completed_scenes))
        return final_url
