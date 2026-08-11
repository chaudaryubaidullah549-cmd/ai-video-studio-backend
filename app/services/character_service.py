"""Character system: builds the Character Bible from the Story."""
from __future__ import annotations

import json
import uuid

from app.models.character import Character, VoiceCharacteristics
from app.models.generation import Story
from app.providers.base import LLMProvider
from app.utils.errors import AppError
from app.utils.logging import get_logger, log_event
from app.services.story_service import _strip_fences

logger = get_logger(__name__)

SYSTEM_PROMPT = """[CHARACTER_EXTRACTION]
You are a character designer for cinematic video generation. Given a
structured story, produce a Character Bible as a single JSON object:

{
  "characters": [
    {
      "name": string,
      "role": "protagonist" | "antagonist" | "supporting",
      "age": string,
      "gender": string,
      "physical_appearance": string,
      "face_description": string,
      "hair": string,
      "clothing": string,
      "body_type": string,
      "personality": string,
      "voice": {"tone": string, "pitch": "low"|"medium"|"high", "pace": "slow"|"medium"|"fast", "accent": string},
      "important_props": [string, ...]
    }
  ]
}

Every field must be visually concrete and specific enough to condition an
AI video model consistently across multiple independent shots. Respond
with ONLY the JSON object.
"""


class CharacterService:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def build_character_bible(self, story: Story) -> list[Character]:
        user_prompt = (
            f"Story title: {story.title}\n"
            f"Logline: {story.logline}\n"
            f"Setting: {story.setting}\n"
            f"Beginning: {story.beginning}\n"
            f"Conflict: {story.conflict}\n"
            f"Main action: {story.main_action}\n"
            f"Ending: {story.ending}\n"
            f"Named characters mentioned: {', '.join(story.character_names) or 'none specified'}\n"
            "Produce the Character Bible JSON now."
        )
        log_event(logger, "info", "character.build.start", story_title=story.title)
        raw = await self.llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_mode=True,
            max_tokens=2000,
            temperature=0.8,
        )
        try:
            data = json.loads(_strip_fences(raw))
            characters = []
            for c in data.get("characters", []):
                voice = VoiceCharacteristics(**c.get("voice", {})) if isinstance(c.get("voice"), dict) else VoiceCharacteristics()
                characters.append(
                    Character(
                        id=str(uuid.uuid4()),
                        name=c.get("name", "Unnamed"),
                        role=c.get("role", "supporting"),
                        age=c.get("age"),
                        gender=c.get("gender"),
                        physical_appearance=c.get("physical_appearance", ""),
                        face_description=c.get("face_description", ""),
                        hair=c.get("hair", ""),
                        clothing=c.get("clothing", ""),
                        body_type=c.get("body_type", ""),
                        personality=c.get("personality", ""),
                        voice=voice,
                        important_props=c.get("important_props", []),
                    )
                )
        except Exception as e:  # noqa: BLE001
            log_event(logger, "error", "character.build.parse_error", error=str(e), raw=raw[:500])
            raise AppError(
                "Failed to parse character bible from LLM response",
                code="CHARACTER_BUILD_ERROR",
                status_code=502,
                retryable=True,
            ) from e

        if not characters:
            raise AppError(
                "LLM returned no characters", code="CHARACTER_BUILD_ERROR", status_code=502, retryable=True
            )
        log_event(logger, "info", "character.build.success", count=len(characters))
        return characters
