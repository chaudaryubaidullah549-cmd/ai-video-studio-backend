"""
Cross-cutting generation models: the structured Story representation, and
generic provider result/status types shared by all provider adapters.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Story(BaseModel):
    """Structured story representation produced by the Story Engine.

    Deliberately structured (not raw prose) so downstream services
    (character extraction, scene planning) can consume it deterministically.
    """

    title: str
    logline: str
    beginning: str
    conflict: str
    main_action: str
    ending: str
    setting: str
    themes: List[str] = Field(default_factory=list)
    tone: List[str] = Field(default_factory=list)
    narration_style: str = Field(
        default="third-person cinematic", description="How narration lines should read"
    )
    character_names: List[str] = Field(
        default_factory=list, description="Names mentioned, used to seed character extraction"
    )
    scene_beats: List[str] = Field(
        default_factory=list,
        description="Ordered list of short beat descriptions used to derive scenes",
    )


class ProviderTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProviderGenerationResult(BaseModel):
    """Normalized result returned by any generation-capable provider."""

    task_id: str
    status: ProviderTaskStatus
    output_url: Optional[str] = None
    output_local_path: Optional[str] = None
    error_message: Optional[str] = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
