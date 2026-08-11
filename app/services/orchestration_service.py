"""Orchestration service: runs the full pipeline for a project.

USER PROMPT -> STORY -> CHARACTER BIBLE -> SCENE PLAN -> SHOT PROMPTS ->
VIDEO GENERATION -> VOICE/DIALOGUE -> MUSIC -> SOUND EFFECTS -> VIDEO
EDITING -> FINAL MP4

This is invoked from a background task (see workers/generation_worker.py)
so the API layer never blocks the HTTP request on generation. Each stage
updates project.status and is persisted via the repository so
GET /status always reflects current progress, even mid-pipeline.
"""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.database import SessionLocal
from app.models.enums import ProjectStatus, SceneStatus
from app.models.project import Project
from app.providers.llm import get_llm_provider
from app.providers.video import get_video_provider
from app.providers.voice import get_voice_provider
from app.providers.music import get_music_provider, get_sfx_provider
from app.providers.storage import get_storage_provider
from app.services.character_service import CharacterService
from app.services.music_service import MusicService
from app.services.project_repository import ProjectRepository
from app.services.render_service import RenderService
from app.services.scene_service import SceneService
from app.services.story_service import StoryService
from app.services.video_service import VideoService
from app.services.voice_service import VoiceService
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()

# Bounded concurrency for per-scene generation so we don't hammer the
# provider (and, in MOCK_MODE, don't spawn unbounded ffmpeg processes).
SCENE_CONCURRENCY = 3

# Per-project locks guarding the read-modify-write sequence used when
# persisting a single scene's result. Concurrent scene tasks each load
# the full Project row, mutate one scene, and save the whole row back
# (see database.py's document-per-row design) - without serializing that
# sequence, two tasks finishing close together can race: both load the
# same "before" state, and whichever saves last silently discards the
# other's update. The actual provider calls (video/voice/music
# generation) still run fully concurrently; only the persist step is
# serialized.
_project_locks: dict[str, asyncio.Lock] = {}


def _lock_for(project_id: str) -> asyncio.Lock:
    lock = _project_locks.get(project_id)
    if lock is None:
        lock = asyncio.Lock()
        _project_locks[project_id] = lock
    return lock


class OrchestrationService:
    def __init__(self):
        self.storage = get_storage_provider()
        self.llm = get_llm_provider()
        self.video_provider = get_video_provider()
        self.voice_provider = get_voice_provider()
        self.music_provider = get_music_provider()
        self.sfx_provider = get_sfx_provider()

        self.story_service = StoryService(self.llm)
        self.character_service = CharacterService(self.llm)
        self.scene_service = SceneService(self.llm)
        self.video_service = VideoService(self.video_provider, self.storage)
        self.voice_service = VoiceService(self.voice_provider, self.storage)
        self.music_service = MusicService(self.music_provider, self.sfx_provider, self.storage)
        self.render_service = RenderService(self.storage)

    def _save(self, project: Project) -> None:
        db = SessionLocal()
        try:
            ProjectRepository(db).save(project)
        finally:
            db.close()

    def _load(self, project_id: str) -> Project:
        db = SessionLocal()
        try:
            return ProjectRepository(db).get(project_id)
        finally:
            db.close()

    async def run_pipeline(self, project_id: str) -> None:
        try:
            project = self._load(project_id)
            project = await self._run_story_and_characters(project)
            project = await self._run_scene_planning(project)
            project = await self._run_scene_generation(project)
            project = await self._run_render(project)

            # Reload immediately before the final save rather than reusing
            # any earlier in-memory reference, so this save can never
            # clobber a later concurrent update (belt-and-suspenders on
            # top of the per-stage reload discipline below).
            project = self._load(project_id)
            project.status = ProjectStatus.COMPLETED
            self._save(project)
            log_event(logger, "info", "orchestration.completed", project_id=project_id)

        except AppError as e:
            project = self._load(project_id)
            project.status = ProjectStatus.FAILED
            project.error = e.message
            self._save(project)
            log_event(logger, "error", "orchestration.failed", project_id=project_id, error=e.message, code=e.code)
        except Exception as e:  # noqa: BLE001
            project = self._load(project_id)
            project.status = ProjectStatus.FAILED
            project.error = f"Unexpected error: {e}"
            self._save(project)
            log_event(logger, "error", "orchestration.unexpected_error", project_id=project_id, error=str(e))

    async def _run_story_and_characters(self, project: Project) -> Project:
        project.status = ProjectStatus.ANALYZING
        self._save(project)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="analyzing")

        story = await self.story_service.plan_story(
            prompt=project.prompt,
            style=project.settings.style,
            duration=project.settings.duration,
            language=project.settings.language,
        )
        project.story = story
        self._save(project)

        project.status = ProjectStatus.GENERATING_CHARACTERS
        self._save(project)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="generating_characters")

        characters = await self.character_service.build_character_bible(story)
        project.characters = characters
        self._save(project)
        return project

    async def _run_scene_planning(self, project: Project) -> Project:
        project.status = ProjectStatus.PLANNING_SCENES
        self._save(project)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="planning_scenes")

        scenes = await self.scene_service.plan_scenes(
            story=project.story,
            characters=project.characters,
            total_duration=project.settings.duration,
            style=project.settings.style,
            aspect_ratio=project.settings.aspect_ratio.value,
        )
        project.scenes = scenes
        self._save(project)
        return project

    async def _run_scene_generation(self, project: Project) -> Project:
        project.status = ProjectStatus.GENERATING_SCENES
        self._save(project)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="generating_scenes")

        semaphore = asyncio.Semaphore(SCENE_CONCURRENCY)
        lock = _lock_for(project.id)
        scene_ids = [s.id for s in project.scenes]

        async def _generate_one(scene_id: str):
            async with semaphore:
                # Read project state (for prompt/character context) without
                # holding the lock - generation itself can run concurrently.
                current = self._load(project.id)
                scene = next(s for s in current.scenes if s.id == scene_id)
                scene = await self.video_service.generate_scene_clip(project=current, scene=scene)

                # Only the load-mutate-save persistence step is serialized,
                # so concurrent scene results can't clobber each other.
                async with lock:
                    fresh = self._load(project.id)
                    self._replace_scene(fresh, scene)
                    self._save(fresh)
                return scene.id

        await asyncio.gather(*[_generate_one(sid) for sid in scene_ids])

        # IMPORTANT: reload before starting the next stage. `project` here
        # is still the object this method was called with; its `.scenes`
        # do NOT reflect the per-scene updates saved above (those went
        # through separate `current`/`fresh` local copies). Continuing to
        # mutate/save the stale `project` object would silently overwrite
        # the video results we just persisted.
        project = self._load(project.id)

        # Audio pass (voice + music + sfx) - depends on video having run
        # so we know final scene durations/status, but proceeds even for
        # scenes whose video failed (so partial audio isn't wasted, and
        # the operator can inspect what succeeded).
        project.status = ProjectStatus.GENERATING_AUDIO
        self._save(project)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="generating_audio")

        async def _audio_one(scene_id: str):
            async with semaphore:
                current = self._load(project.id)
                scene = next(s for s in current.scenes if s.id == scene_id)
                scene = await self.voice_service.generate_scene_audio(project=current, scene=scene)
                scene = await self.music_service.generate_scene_music(project=current, scene=scene)
                scene = await self.music_service.generate_scene_sfx(project=current, scene=scene)

                async with lock:
                    fresh = self._load(project.id)
                    self._replace_scene(fresh, scene)
                    self._save(fresh)
                return scene.id

        await asyncio.gather(*[_audio_one(sid) for sid in scene_ids])

        # Same reasoning as above: return freshly loaded state rather than
        # the stale `project` reference.
        return self._load(project.id)

    async def _run_render(self, project: Project) -> Project:
        current = self._load(project.id)
        current.status = ProjectStatus.EDITING
        self._save(current)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="editing")

        current.status = ProjectStatus.RENDERING
        self._save(current)
        log_event(logger, "info", "orchestration.stage", project_id=project.id, stage="rendering")

        final_url = await self.render_service.render_project(current)

        # Reload once more before attaching final_video_url: rendering can
        # take a while, and we want the save below to build on the latest
        # persisted state rather than the pre-render snapshot in `current`.
        current = self._load(project.id)
        current.final_video_url = final_url
        self._save(current)
        return current

    @staticmethod
    def _replace_scene(project: Project, scene) -> None:
        for i, s in enumerate(project.scenes):
            if s.id == scene.id:
                project.scenes[i] = scene
                return
        project.scenes.append(scene)

    async def regenerate_scene(self, project_id: str, scene_id: str) -> Project:
        project = self._load(project_id)
        scene = next((s for s in project.scenes if s.id == scene_id), None)
        if scene is None:
            raise AppError(f"Scene {scene_id} not found", code="NOT_FOUND", status_code=404)

        scene.status = SceneStatus.PENDING
        scene.error = None
        scene = await self.video_service.generate_scene_clip(project=project, scene=scene)
        scene = await self.voice_service.generate_scene_audio(project=project, scene=scene)
        scene = await self.music_service.generate_scene_music(project=project, scene=scene)
        scene = await self.music_service.generate_scene_sfx(project=project, scene=scene)

        # Reload before saving in case /generate is running concurrently
        # for the same project (best-effort - the API layer already
        # rejects overlapping regenerate calls for the same scene, but a
        # full-project regeneration could be running at the same time).
        fresh = self._load(project_id)
        self._replace_scene(fresh, scene)
        self._save(fresh)
        return fresh
