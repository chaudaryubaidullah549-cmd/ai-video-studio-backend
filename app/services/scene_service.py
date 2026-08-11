"""Scene Engine: breaks the story into scenes sized to fit the requested
total duration, and assembles the final per-scene generation prompt.

Character consistency strategy: the final `generation_prompt` for every
scene is assembled in CODE (not by the LLM) by concatenating each
referenced character's `Character.visual_descriptor()`, which is a pure,
deterministic function of the Character Bible. This guarantees every
scene that references the same character gets an identical description
string, rather than relying on an LLM to remember/repeat details
consistently across separate calls.
"""
from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from app.config import get_settings
from app.models.character import Character
from app.models.enums import AudioMood, CameraMovement, SceneStatus, ShotType, TimeOfDay
from app.models.generation import Story
from app.models.scene import DialogueLine, Scene
from app.providers.base import LLMProvider
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event
from app.services.story_service import _strip_fences

logger = get_logger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """[SCENE_PLANNING]
You are a cinematography and scene-breakdown expert. Given a structured
story and its beat list, produce a shot-by-shot scene plan as JSON:

{
  "scenes": [
    {
      "title": string,
      "location": string,
      "time_of_day": "dawn"|"morning"|"afternoon"|"dusk"|"night"|"unspecified",
      "action": string,
      "narration": string or null,
      "dialogue": [{"character_name": string, "text": string, "emotion": string}],
      "camera_movement": "static"|"pan_left"|"pan_right"|"tilt_up"|"tilt_down"|"dolly_in"|"dolly_out"|"tracking"|"handheld"|"crane",
      "shot_type": "wide"|"medium"|"close_up"|"extreme_close_up"|"establishing"|"over_the_shoulder"|"pov",
      "lighting": string,
      "visual_style": string,
      "audio_mood": "energetic"|"emotional"|"suspense"|"peaceful"|"neutral"|"triumphant"|"ominous"
    }
  ]
}

Produce one scene per beat given. Respond with ONLY the JSON object.
"""


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except Exception:
        return default


class SceneService:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def _distribute_durations(self, total_seconds: int, scene_count: int) -> list[float]:
        if scene_count <= 0:
            return []
        max_scene = settings.MAX_SCENE_DURATION_SECONDS
        # Split evenly, then clamp each scene to MAX_SCENE_DURATION_SECONDS
        # and add more, shorter scenes if the total would otherwise exceed
        # the requested duration - keeps clips short per the spec
        # ("avoid generating one huge video request").
        per_scene = total_seconds / scene_count
        if per_scene <= max_scene:
            durations = [round(per_scene, 1)] * scene_count
        else:
            # Too few beats for the requested duration at max clip length -
            # expand scene count implicitly by capping each at max_scene;
            # remainder is distributed across the last scenes.
            durations = [float(max_scene)] * scene_count
        # Adjust the last scene so the sum matches total as closely as possible.
        diff = total_seconds - sum(durations)
        if durations:
            durations[-1] = max(1.0, round(durations[-1] + diff, 1))
        return durations

    async def plan_scenes(
        self,
        *,
        story: Story,
        characters: list[Character],
        total_duration: int,
        style: str,
        aspect_ratio: str,
    ) -> list[Scene]:
        beats = story.scene_beats or [story.beginning, story.conflict, story.main_action, story.ending]
        user_prompt = (
            f"Story: {story.title} - {story.logline}\n"
            f"Beats (produce exactly one scene per beat, same order):\n"
            + "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats))
            + f"\nCharacters available: {', '.join(c.name for c in characters)}\n"
            f"Visual style requested: {style}\n"
            "Produce the scene plan JSON now."
        )
        log_event(logger, "info", "scene.planning.start", beats=len(beats))
        raw = await self.llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=True,
            max_tokens=3000,
            temperature=0.8,
        )
        try:
            data = json.loads(_strip_fences(raw))
            raw_scenes = data.get("scenes", [])
        except Exception as e:  # noqa: BLE001
            log_event(logger, "error", "scene.planning.parse_error", error=str(e), raw=raw[:500])
            raise AppError(
                "Failed to parse scene plan from LLM response",
                code="SCENE_PLANNING_ERROR",
                status_code=502,
                retryable=True,
            ) from e

        if not raw_scenes:
            raise AppError("LLM returned no scenes", code="SCENE_PLANNING_ERROR", status_code=502, retryable=True)

        durations = self._distribute_durations(total_duration, len(raw_scenes))
        name_to_char = {c.name.lower(): c for c in characters}

        scenes: list[Scene] = []
        for idx, (rs, duration) in enumerate(zip(raw_scenes, durations)):
            dialogue_lines = []
            char_ids_in_scene: list[str] = []
            for d in rs.get("dialogue", []) or []:
                char = name_to_char.get(str(d.get("character_name", "")).lower())
                if char and char.id not in char_ids_in_scene:
                    char_ids_in_scene.append(char.id)
                dialogue_lines.append(
                    DialogueLine(
                        character_id=char.id if char else "unknown",
                        character_name=d.get("character_name", "Unknown"),
                        text=d.get("text", ""),
                        emotion=d.get("emotion"),
                    )
                )

            # Also include characters mentioned only in the action line, by
            # simple name match, so their descriptors get folded into the prompt.
            action_text = rs.get("action", "")
            for c in characters:
                if c.name.lower() in action_text.lower() and c.id not in char_ids_in_scene:
                    char_ids_in_scene.append(c.id)

            scene = Scene(
                id=str(uuid.uuid4()),
                index=idx,
                title=rs.get("title", f"Scene {idx + 1}"),
                duration=duration,
                location=rs.get("location", ""),
                time_of_day=_safe_enum(TimeOfDay, rs.get("time_of_day"), TimeOfDay.UNSPECIFIED),
                character_ids=char_ids_in_scene,
                action=action_text,
                dialogue=dialogue_lines,
                narration=rs.get("narration"),
                camera_movement=_safe_enum(CameraMovement, rs.get("camera_movement"), CameraMovement.STATIC),
                shot_type=_safe_enum(ShotType, rs.get("shot_type"), ShotType.MEDIUM),
                lighting=rs.get("lighting", ""),
                visual_style=rs.get("visual_style", style),
                audio_mood=_safe_enum(AudioMood, rs.get("audio_mood"), AudioMood.NEUTRAL),
                status=SceneStatus.PENDING,
            )
            scene.generation_prompt = self._build_generation_prompt(
                scene=scene, characters=[name_to_char[c.name.lower()] for c in characters if c.id in char_ids_in_scene], style=style, aspect_ratio=aspect_ratio
            )
            scenes.append(scene)

        log_event(logger, "info", "scene.planning.success", count=len(scenes))
        return scenes

    def _build_generation_prompt(
        self, *, scene: Scene, characters: list[Character], style: str, aspect_ratio: str
    ) -> str:
        parts = [f"{style} style video shot."]
        if scene.shot_type:
            parts.append(f"{scene.shot_type.value.replace('_', ' ')} shot,")
        if scene.camera_movement:
            parts.append(f"camera movement: {scene.camera_movement.value.replace('_', ' ')}.")
        if scene.location:
            parts.append(f"Setting: {scene.location}" + (f", {scene.time_of_day.value}" if scene.time_of_day != TimeOfDay.UNSPECIFIED else "") + ".")
        if scene.lighting:
            parts.append(f"Lighting: {scene.lighting}.")
        if scene.action:
            parts.append(f"Action: {scene.action}")
        for c in characters:
            parts.append(f"Character - {c.visual_descriptor()}.")
        if scene.visual_style:
            parts.append(f"Visual style: {scene.visual_style}.")
        parts.append(f"Aspect ratio {aspect_ratio}.")
        return " ".join(p for p in parts if p)

    def rebuild_prompt_for_scene(self, scene: Scene, characters: list[Character], style: str, aspect_ratio: str) -> str:
        chars = [c for c in characters if c.id in scene.character_ids]
        return self._build_generation_prompt(scene=scene, characters=chars, style=style, aspect_ratio=aspect_ratio)
