from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import AudioMood, CameraMovement, SceneStatus, ShotType, TimeOfDay


class DialogueLine(BaseModel):
    character_id: str
    character_name: str
    text: str
    emotion: Optional[str] = None


class SceneMedia(BaseModel):
    """Output artifacts attached to a scene once generation completes."""

    video_url: Optional[str] = None
    voice_track_urls: List[str] = Field(default_factory=list)
    music_url: Optional[str] = None
    sfx_urls: List[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None


class Scene(BaseModel):
    id: str
    index: int
    title: str
    duration: float = Field(description="Target duration in seconds")

    location: str = ""
    time_of_day: TimeOfDay = TimeOfDay.UNSPECIFIED
    character_ids: List[str] = Field(default_factory=list)

    action: str = ""
    dialogue: List[DialogueLine] = Field(default_factory=list)
    narration: Optional[str] = None

    camera_movement: CameraMovement = CameraMovement.STATIC
    shot_type: ShotType = ShotType.MEDIUM
    lighting: str = ""
    visual_style: str = ""

    audio_mood: AudioMood = AudioMood.NEUTRAL

    negative_prompt: str = (
        "blurry, distorted, extra limbs, disfigured, low quality, watermark, text overlay"
    )
    generation_prompt: str = Field(
        default="", description="Final assembled prompt sent to the video provider"
    )

    status: SceneStatus = SceneStatus.PENDING
    provider_task_id: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None

    media: SceneMedia = Field(default_factory=SceneMedia)
