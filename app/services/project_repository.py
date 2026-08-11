"""
Repository layer: translates between the Project pydantic model and the
ProjectRecord SQLAlchemy row. Services should never touch SQLAlchemy
directly - they go through this repository, which keeps the persistence
mechanism swappable (SQLite -> Postgres, or JSON-blob -> normalized
tables) without touching business logic.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.database import ProjectRecord
from app.models.project import Project
from app.utils.errors import NotFoundError


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, project: Project) -> Project:
        record = ProjectRecord(
            id=project.id,
            status=project.status.value,
            data=json.loads(project.model_dump_json()),
        )
        self.db.add(record)
        self.db.commit()
        return project

    def get(self, project_id: str) -> Project:
        record = self.db.get(ProjectRecord, project_id)
        if record is None:
            raise NotFoundError(f"Project {project_id} not found")
        return Project.model_validate(record.data)

    def get_or_none(self, project_id: str) -> Optional[Project]:
        record = self.db.get(ProjectRecord, project_id)
        if record is None:
            return None
        return Project.model_validate(record.data)

    def save(self, project: Project) -> Project:
        record = self.db.get(ProjectRecord, project.id)
        if record is None:
            raise NotFoundError(f"Project {project.id} not found")
        record.status = project.status.value
        record.data = json.loads(project.model_dump_json())
        self.db.add(record)
        self.db.commit()
        return project

    def delete(self, project_id: str) -> None:
        record = self.db.get(ProjectRecord, project_id)
        if record is None:
            raise NotFoundError(f"Project {project_id} not found")
        self.db.delete(record)
        self.db.commit()
