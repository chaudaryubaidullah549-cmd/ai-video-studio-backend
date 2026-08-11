"""Voice/dialogue generation service: synthesizes narration + per-line
dialogue for a scene and stores the resulting audio tracks."""
from __future__ import annotations

from app.config import get_settings
from app.models.project import Project
from app.models.scene import Scene
from app.providers.base import StorageProvider, VoiceProvider
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


class VoiceService:
    def __init__(self, voice_provider: VoiceProvider, storage: StorageProvider):
        self.voice_provider = voice_provider
        self.storage = storage

    async def generate_scene_audio(self, *, project: Project, scene: Scene) -> Scene:
        chars_by_id = {c.id: c for c in project.characters}
        track_urls: list[str] = []

        if scene.narration:
            try:
                result = await self.voice_provider.generate_speech(
                    text=scene.narration, voice=project.settings.voice, language=project.settings.language
                )
                rel = f"projects/{project.id}/scenes/{scene.id}/narration.wav"
                dest = self.storage.get_absolute_path(rel)
                await self.voice_provider.download_result(result.task_id, dest)
                track_urls.append(self.storage.url_for(rel))
            except AppError as e:
                log_event(logger, "warning", "voice.narration.failed", project_id=project.id, scene_id=scene.id, error=e.message)

        for i, line in enumerate(scene.dialogue):
            character = chars_by_id.get(line.character_id)
            voice_chars = character.voice.model_dump() if character else {}
            try:
                result = await self.voice_provider.generate_dialogue(
                    character_name=line.character_name,
                    text=line.text,
                    voice_characteristics=voice_chars,
                    language=project.settings.language,
                )
                rel = f"projects/{project.id}/scenes/{scene.id}/dialogue_{i}.wav"
                dest = self.storage.get_absolute_path(rel)
                await self.voice_provider.download_result(result.task_id, dest)
                track_urls.append(self.storage.url_for(rel))
            except AppError as e:
                log_event(
                    logger, "warning", "voice.dialogue.failed",
                    project_id=project.id, scene_id=scene.id, character=line.character_name, error=e.message,
                )

        scene.media.voice_track_urls = track_urls
        return scene
