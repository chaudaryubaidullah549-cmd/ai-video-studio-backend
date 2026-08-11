"""
Project endpoints.

  POST   /api/projects
  GET    /api/projects/{project_id}
  GET    /api/projects/{project_id}/status
  POST   /api/projects/{project_id}/generate
  GET    /api/projects/{project_id}/download
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project, ProjectCreateRequest, ProjectStatusResponse
from app.providers.storage import get_storage_provider
from app.services.project_repository import ProjectRepository
from app.services.project_service import ProjectService
from app.utils.errors import AppError, ConflictError, NotFoundError
from app.utils.logging import get_logger, log_event
from app.workers.generation_worker import enqueue_generation, is_running

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = get_logger(__name__)


@router.post("", response_model=Project, status_code=201)
async def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)) -> Project:
    project = ProjectService.build_new_project(payload)
    repo = ProjectRepository(db)
    repo.create(project)
    return project


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    repo = ProjectRepository(db)
    return repo.get(project_id)


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(project_id: str, db: Session = Depends(get_db)) -> ProjectStatusResponse:
    repo = ProjectRepository(db)
    project = repo.get(project_id)
    return ProjectService.compute_status_response(project)


@router.post("/{project_id}/generate", response_model=ProjectStatusResponse, status_code=202)
async def start_generation(project_id: str, db: Session = Depends(get_db)) -> ProjectStatusResponse:
    repo = ProjectRepository(db)
    project = repo.get(project_id)  # raises NotFoundError if missing

    if is_running(project_id):
        raise ConflictError(f"Generation is already running for project {project_id}")

    enqueue_generation(project_id)
    log_event(logger, "info", "api.generate.started", project_id=project_id)
    return ProjectService.compute_status_response(project)


@router.get("/{project_id}/download")
async def download_project(project_id: str, db: Session = Depends(get_db)):
    repo = ProjectRepository(db)
    project = repo.get(project_id)

    if not project.final_video_url:
        raise AppError(
            "Final video is not available yet. Check /status for pipeline progress.",
            code="VIDEO_NOT_READY",
            status_code=409,
            retryable=True,
        )

    storage = get_storage_provider()
    path = storage.local_path_for_url(project.final_video_url)
    if not os.path.exists(path):
        raise NotFoundError("Final video file is missing from storage")

    return FileResponse(path, media_type="video/mp4", filename=f"{project_id}.mp4")
