"""Video generation service: drives the VideoProvider per scene, with
retries, and persists the resulting clip through the StorageProvider.
Never marks a failed generation as successful.
"""
from __future__ import annotations

import os

from app.config import get_settings
from app.models.enums import SceneStatus
from app.models.generation import ProviderTaskStatus
from app.models.project import Project
from app.models.scene import Scene
from app.providers.base import StorageProvider, VideoProvider
from app.utils.errors import AppError, VideoProviderError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()


class VideoService:
    def __init__(self, video_provider: VideoProvider, storage: StorageProvider):
        self.video_provider = video_provider
        self.storage = storage

    async def generate_scene_clip(self, *, project: Project, scene: Scene) -> Scene:
        scene.status = SceneStatus.GENERATING
        scene.error = None
        max_attempts = settings.PROVIDER_MAX_RETRIES
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                log_event(
                    logger, "info", "video.generate.attempt",
                    project_id=project.id, scene_id=scene.id, attempt=attempt,
                )
                # Prefer image-to-video if any referenced character has a
                # reference image (see Character.reference_image_url) -
                # improves, but per VideoProvider contract never
                # guarantees, visual consistency.
                reference_url = self._first_reference_image(project, scene)
                if reference_url:
                    result = await self.video_provider.generate_image_to_video(
                        prompt=scene.generation_prompt,
                        reference_image_url=reference_url,
                        negative_prompt=scene.negative_prompt,
                        duration_seconds=scene.duration,
                        aspect_ratio=project.settings.aspect_ratio.value,
                    )
                else:
                    result = await self.video_provider.generate_text_to_video(
                        prompt=scene.generation_prompt,
                        negative_prompt=scene.negative_prompt,
                        duration_seconds=scene.duration,
                        aspect_ratio=project.settings.aspect_ratio.value,
                    )

                if result.status != ProviderTaskStatus.SUCCEEDED:
                    # Never silently mark a failed generation as successful.
                    raise VideoProviderError(
                        result.error_message or "Video provider returned a non-success status",
                    )

                relative_path = f"projects/{project.id}/scenes/{scene.id}/clip_raw.mp4"
                local_temp = result.output_local_path
                if local_temp:
                    url = self.storage.save_file_from_path(relative_path=relative_path, source_path=local_temp)
                else:
                    dest = self.storage.get_absolute_path(relative_path)
                    await self.video_provider.download_result(result.task_id, dest)
                    url = self.storage.url_for(relative_path)

                scene.media.video_url = url
                scene.provider_task_id = result.task_id
                scene.status = SceneStatus.COMPLETED
                scene.retry_count = attempt - 1
                log_event(logger, "info", "video.generate.success", project_id=project.id, scene_id=scene.id)
                return scene

            except AppError as e:
                last_error = e
                log_event(
                    logger, "warning", "video.generate.failed_attempt",
                    project_id=project.id, scene_id=scene.id, attempt=attempt,
                    error=e.message, retryable=e.retryable,
                )
                if not e.retryable or attempt == max_attempts:
                    break
            except Exception as e:  # noqa: BLE001
                last_error = e
                log_event(
                    logger, "error", "video.generate.unexpected_error",
                    project_id=project.id, scene_id=scene.id, attempt=attempt, error=str(e),
                )
                break

        scene.status = SceneStatus.FAILED
        scene.retry_count = max_attempts
        scene.error = str(last_error) if last_error else "Unknown video generation error"
        log_event(logger, "error", "video.generate.exhausted", project_id=project.id, scene_id=scene.id, error=scene.error)
        return scene

    def _first_reference_image(self, project: Project, scene: Scene) -> str | None:
        chars_by_id = {c.id: c for c in project.characters}
        for cid in scene.character_ids:
            c = chars_by_id.get(cid)
            if c and c.reference_image_url:
                return c.reference_image_url
        return None
