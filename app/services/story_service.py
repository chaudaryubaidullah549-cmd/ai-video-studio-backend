"""Story Engine: turns the user's single natural-language prompt into a
structured Story object via the configured LLMProvider."""
from __future__ import annotations

import json

from app.models.generation import Story
from app.providers.base import LLMProvider
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)

# The "STORY_PLANNING" marker lets MockLLMProvider route to the right
# canned JSON shape; real providers just see it as part of the system
# prompt text and ignore it.
SYSTEM_PROMPT = """[STORY_PLANNING]
You are a professional story architect for short cinematic videos.
Given a user's natural-language video concept, produce a structured story
as a single JSON object with EXACTLY these fields:

{
  "title": string,
  "logline": string,
  "beginning": string,
  "conflict": string,
  "main_action": string,
  "ending": string,
  "setting": string,
  "themes": [string, ...],
  "tone": [string, ...],
  "narration_style": string,
  "character_names": [string, ...],
  "scene_beats": [string, ...]   // ordered short beat descriptions, 3-8 beats
}

Respond with ONLY the JSON object, no commentary, no markdown fences.
"""


class StoryService:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def plan_story(self, *, prompt: str, style: str, duration: int, language: str) -> Story:
        user_prompt = (
            f"User concept: {prompt}\n"
            f"Visual style: {style}\n"
            f"Target duration: {duration} seconds\n"
            f"Language: {language}\n"
            "Produce the structured story JSON now."
        )
        log_event(logger, "info", "story.planning.start", prompt_len=len(prompt))
        raw = await self.llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=True,
            max_tokens=1500,
            temperature=0.9,
        )
        try:
            data = json.loads(_strip_fences(raw))
            story = Story.model_validate(data)
        except Exception as e:  # noqa: BLE001
            log_event(logger, "error", "story.planning.parse_error", error=str(e), raw=raw[:500])
            raise AppError(
                "Failed to parse story plan from LLM response",
                code="STORY_PLANNING_ERROR",
                status_code=502,
                retryable=True,
            ) from e
        log_event(logger, "info", "story.planning.success", title=story.title, beats=len(story.scene_beats))
        return story


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()
