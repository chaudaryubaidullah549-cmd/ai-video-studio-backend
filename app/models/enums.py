from __future__ import annotations

from enum import Enum


class ProjectStatus(str, Enum):
    PLANNED = "planned"
    ANALYZING = "analyzing"
    PLANNING_SCENES = "planning_scenes"
    GENERATING_CHARACTERS = "generating_characters"
    GENERATING_SCENES = "generating_scenes"
    GENERATING_AUDIO = "generating_audio"
    EDITING = "editing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class SceneStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AspectRatio(str, Enum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    SQUARE = "1:1"


class ShotType(str, Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    ESTABLISHING = "establishing"
    OVER_THE_SHOULDER = "over_the_shoulder"
    POV = "pov"


class CameraMovement(str, Enum):
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACKING = "tracking"
    HANDHELD = "handheld"
    CRANE = "crane"


class AudioMood(str, Enum):
    ENERGETIC = "energetic"
    EMOTIONAL = "emotional"
    SUSPENSE = "suspense"
    PEACEFUL = "peaceful"
    NEUTRAL = "neutral"
    TRIUMPHANT = "triumphant"
    OMINOUS = "ominous"


class TimeOfDay(str, Enum):
    DAWN = "dawn"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    DUSK = "dusk"
    NIGHT = "night"
    UNSPECIFIED = "unspecified"
