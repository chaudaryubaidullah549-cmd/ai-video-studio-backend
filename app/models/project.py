from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.character import Character
from app.models.enums import AspectRatio, ProjectStatus
from app.models.generation import Story
from app.models.scene import Scene


def new_id() -> str:
    return str(uuid.uuid4())


class ProjectCreateRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)
    duration: int = Field(default=20, ge=5, le=180, description="Target total duration, seconds")
    style: str = Field(default="cinematic", max_length=100)
    aspect_ratio: AspectRatio = Field(default=AspectRatio.LANDSCAPE)
    language: str = Field(default="en", max_length=10)
    voice: str = Field(default="auto", max_length=50)

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be blank")
        return v


class ProjectSettings(BaseModel):
    duration: int
    style: str
    aspect_ratio: AspectRatio
    language: str
    voice: str


class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    status: ProjectStatus = ProjectStatus.PLANNED
    prompt: str
    settings: ProjectSettings

    story: Optional[Story] = None
    characters: List[Character] = Field(default_factory=list)
    scenes: List[Scene] = Field(default_factory=list)

    final_video_url: Optional[str] = None
    error: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_response(self) -> "Project":
        return self


class ProjectStatusResponse(BaseModel):
    id: str
    status: ProjectStatus
    progress_percent: int
    current_step: str
    scenes_total: int
    scenes_completed: int
    scenes_failed: int
    error: Optional[str] = None
    updated_at: datetime


class SceneRegenerateRequest(BaseModel):
    # Optional creative override for the regeneration pass.
    instructions: Optional[str] = Field(default=None, max_length=1000)
