"""
Background job runner for the generation pipeline.

Design: in-process asyncio tasks, tracked in a small registry so a
project can't be double-enqueued and so the API can report "already
running" instead of silently starting a second pipeline. This keeps the
reference implementation dependency-light (no Redis/Celery required to
run locally or with MOCK_MODE=true).

For a multi-process/production deployment, swap `enqueue_generation` for
a real task queue (Celery, RQ, Arq, etc.) that calls
`OrchestrationService.run_pipeline(project_id)` from a worker process -
no other application code needs to change, since the orchestration
service already reloads project state from the database at each stage
rather than relying on in-memory object identity.
"""
from __future__ import annotations

import asyncio

from app.services.orchestration_service import OrchestrationService
from app.utils.errors import ConflictError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}


def is_running(project_id: str) -> bool:
    task = _running_tasks.get(project_id)
    return task is not None and not task.done()


def enqueue_generation(project_id: str) -> None:
    if is_running(project_id):
        raise ConflictError(f"Generation is already running for project {project_id}")

    async def _run():
        service = OrchestrationService()
        try:
            await service.run_pipeline(project_id)
        finally:
            _running_tasks.pop(project_id, None)

    log_event(logger, "info", "worker.enqueue", project_id=project_id)
    task = asyncio.create_task(_run())
    _running_tasks[project_id] = task


def enqueue_scene_regeneration(project_id: str, scene_id: str) -> None:
    key = f"{project_id}:{scene_id}"
    if is_running(key):
        raise ConflictError(f"Regeneration already running for scene {scene_id}")

    async def _run():
        service = OrchestrationService()
        try:
            await service.regenerate_scene(project_id, scene_id)
        finally:
            _running_tasks.pop(key, None)

    log_event(logger, "info", "worker.enqueue_scene_regen", project_id=project_id, scene_id=scene_id)
    task = asyncio.create_task(_run())
    _running_tasks[key] = task
