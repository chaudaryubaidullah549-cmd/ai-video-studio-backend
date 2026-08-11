"""Project-level service: creation and status computation."""
from __future__ import annotations

from app.config import get_settings
from app.models.enums import ProjectStatus, SceneStatus
from app.models.project import Project, ProjectCreateRequest, ProjectSettings, ProjectStatusResponse
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)
settings = get_settings()

_STATUS_ORDER = [
    ProjectStatus.PLANNED,
    ProjectStatus.ANALYZING,
    ProjectStatus.PLANNING_SCENES,
    ProjectStatus.GENERATING_CHARACTERS,
    ProjectStatus.GENERATING_SCENES,
    ProjectStatus.GENERATING_AUDIO,
    ProjectStatus.EDITING,
    ProjectStatus.RENDERING,
    ProjectStatus.COMPLETED,
]

_STATUS_LABELS = {
    ProjectStatus.PLANNED: "Queued",
    ProjectStatus.ANALYZING: "Analyzing prompt & planning story",
    ProjectStatus.PLANNING_SCENES: "Breaking story into scenes",
    ProjectStatus.GENERATING_CHARACTERS: "Building character bible",
    ProjectStatus.GENERATING_SCENES: "Generating video clips",
    ProjectStatus.GENERATING_AUDIO: "Generating voice, music & sound effects",
    ProjectStatus.EDITING: "Assembling scenes",
    ProjectStatus.RENDERING: "Rendering final video",
    ProjectStatus.COMPLETED: "Completed",
    ProjectStatus.FAILED: "Failed",
}


class ProjectService:
    @staticmethod
    def build_new_project(request: ProjectCreateRequest) -> Project:
        max_duration = settings.MAX_PROJECT_DURATION_SECONDS
        duration = min(request.duration, max_duration)
        project = Project(
            prompt=request.prompt,
            settings=ProjectSettings(
                duration=duration,
                style=request.style,
                aspect_ratio=request.aspect_ratio,
                language=request.language,
                voice=request.voice,
            ),
            status=ProjectStatus.PLANNED,
        )
        log_event(logger, "info", "project.created", project_id=project.id, duration=duration, style=request.style)
        return project

    @staticmethod
    def compute_status_response(project: Project) -> ProjectStatusResponse:
        total = len(project.scenes)
        completed = sum(1 for s in project.scenes if s.status == SceneStatus.COMPLETED)
        failed = sum(1 for s in project.scenes if s.status == SceneStatus.FAILED)

        if project.status == ProjectStatus.FAILED:
            progress = 0 if total == 0 else int(100 * completed / max(total, 1))
        elif project.status in _STATUS_ORDER:
            stage_idx = _STATUS_ORDER.index(project.status)
            base = int(100 * stage_idx / (len(_STATUS_ORDER) - 1))
            # Within GENERATING_SCENES/GENERATING_AUDIO, blend in scene completion.
            if project.status in (ProjectStatus.GENERATING_SCENES, ProjectStatus.GENERATING_AUDIO) and total:
                stage_span = 100 / (len(_STATUS_ORDER) - 1)
                base = int(base - stage_span + stage_span * (completed / total))
            progress = max(0, min(100, base))
        else:
            progress = 0

        return ProjectStatusResponse(
            id=project.id,
            status=project.status,
            progress_percent=progress,
            current_step=_STATUS_LABELS.get(project.status, project.status.value),
            scenes_total=total,
            scenes_completed=completed,
            scenes_failed=failed,
            error=project.error,
            updated_at=project.updated_at,
        )
