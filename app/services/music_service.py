"""Music/SFX service: picks mood-appropriate music per scene and
generates simple sound effects for key action beats."""
from __future__ import annotations

from app.models.project import Project
from app.models.scene import Scene
from app.providers.base import MusicProvider, SoundEffectProvider, StorageProvider
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)


class MusicService:
    def __init__(self, music_provider: MusicProvider, sfx_provider: SoundEffectProvider, storage: StorageProvider):
        self.music_provider = music_provider
        self.sfx_provider = sfx_provider
        self.storage = storage

    async def generate_scene_music(self, *, project: Project, scene: Scene) -> Scene:
        try:
            result = await self.music_provider.generate_music(
                mood=scene.audio_mood.value, duration_seconds=scene.duration, style=project.settings.style
            )
            rel = f"projects/{project.id}/scenes/{scene.id}/music.wav"
            dest = self.storage.get_absolute_path(rel)
            await self.music_provider.download_result(result.task_id, dest)
            scene.media.music_url = self.storage.url_for(rel)
        except AppError as e:
            log_event(logger, "warning", "music.generate.failed", project_id=project.id, scene_id=scene.id, error=e.message)
        return scene

    async def generate_scene_sfx(self, *, project: Project, scene: Scene) -> Scene:
        if not scene.action:
            return scene
        try:
            result = await self.sfx_provider.generate_sfx(
                description=scene.action, duration_seconds=min(scene.duration, 3.0)
            )
            rel = f"projects/{project.id}/scenes/{scene.id}/sfx_0.wav"
            dest = self.storage.get_absolute_path(rel)
            await self.sfx_provider.download_result(result.task_id, dest)
            scene.media.sfx_urls = [self.storage.url_for(rel)]
        except AppError as e:
            log_event(logger, "warning", "sfx.generate.failed", project_id=project.id, scene_id=scene.id, error=e.message)
        return scene
