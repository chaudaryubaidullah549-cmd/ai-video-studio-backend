"""
Scene endpoints.

  POST /api/projects/{project_id}/scenes/{scene_id}/regenerate
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import SceneRegenerateRequest
from app.models.scene import Scene
from app.services.project_repository import ProjectRepository
from app.utils.errors import ConflictError, NotFoundError
from app.utils.logging import get_logger, log_event
from app.workers.generation_worker import enqueue_scene_regeneration, is_running

router = APIRouter(prefix="/api/projects", tags=["scenes"])
logger = get_logger(__name__)


@router.post("/{project_id}/scenes/{scene_id}/regenerate", response_model=Scene, status_code=202)
async def regenerate_scene(
    project_id: str, scene_id: str, payload: SceneRegenerateRequest | None = None, db: Session = Depends(get_db)
) -> Scene:
    repo = ProjectRepository(db)
    project = repo.get(project_id)
    scene = next((s for s in project.scenes if s.id == scene_id), None)
    if scene is None:
        raise NotFoundError(f"Scene {scene_id} not found in project {project_id}")

    key = f"{project_id}:{scene_id}"
    if is_running(key):
        raise ConflictError(f"Regeneration already running for scene {scene_id}")

    if payload and payload.instructions:
        scene.action = f"{scene.action}\n(Regeneration note: {payload.instructions})"
        repo.save(project)

    enqueue_scene_regeneration(project_id, scene_id)
    log_event(logger, "info", "api.scene_regenerate.started", project_id=project_id, scene_id=scene_id)
    return scene
