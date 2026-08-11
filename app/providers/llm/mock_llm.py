"""
Mock LLM provider used when MOCK_MODE=true.

Instead of calling any external API, this returns deterministic,
well-formed JSON (when json_mode=True) built from the user prompt, so the
story/character/scene services can run their real parsing logic against
realistic-looking structured output.
"""
from __future__ import annotations

import json
import re

from app.providers.base import LLMProvider
from app.utils.logging import get_logger, log_event

logger = get_logger(__name__)


def _keywords(text: str, n: int = 3) -> list[str]:
    words = re.findall(r"[A-Za-z]{4,}", text)
    seen: list[str] = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.append(lw)
        if len(seen) >= n:
            break
    return seen or ["adventure"]


class MockLLMProvider(LLMProvider):
    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        max_tokens: int = 2000,
        temperature: float = 0.8,
    ) -> str:
        log_event(logger, "info", "mock_llm.complete", json_mode=json_mode, prompt_len=len(user_prompt))

        if not json_mode:
            return (
                "This is mock narration generated locally because MOCK_MODE=true. "
                f"Prompt keywords: {', '.join(_keywords(user_prompt))}."
            )

        # Route based on a marker the services embed in their system
        # prompts, so the mock provider returns the right JSON *shape*
        # for whichever pipeline stage is calling it.
        if "STORY_PLANNING" in system_prompt:
            return json.dumps(_mock_story(user_prompt))
        if "CHARACTER_EXTRACTION" in system_prompt:
            return json.dumps(_mock_characters(user_prompt))
        if "SCENE_PLANNING" in system_prompt:
            return json.dumps(_mock_scenes(user_prompt))
        return json.dumps({"result": "mock", "note": "unrecognized json_mode task"})


def _mock_story(user_prompt: str) -> dict:
    kws = _keywords(user_prompt, 3)
    title = " ".join(w.capitalize() for w in kws[:2]) or "Untitled Story"
    return {
        "title": title,
        "logline": f"A story about {', '.join(kws)}.",
        "beginning": f"Our journey begins as the hero encounters {kws[0]}.",
        "conflict": f"A force tied to {kws[-1]} threatens everything.",
        "main_action": f"The hero confronts the challenge of {kws[0]} head-on.",
        "ending": "The hero emerges transformed, having overcome the central conflict.",
        "setting": "A richly detailed, atmospheric world suited to the requested style.",
        "themes": kws,
        "tone": ["mysterious", "emotional"],
        "narration_style": "third-person cinematic",
        "character_names": ["Kael", "Mira"],
        "scene_beats": [
            "Establishing shot of the world and the hero's ordinary life.",
            "An inciting event disrupts the hero's world.",
            "The hero commits to the journey and faces the first obstacle.",
            "A moment of connection or revelation with an ally.",
            "The climactic confrontation with the central conflict.",
            "Resolution and emotional payoff.",
        ],
    }


def _mock_characters(user_prompt: str) -> dict:
    return {
        "characters": [
            {
                "name": "Kael",
                "role": "protagonist",
                "age": "24",
                "gender": "male",
                "physical_appearance": "lean and weathered, sun-tanned skin",
                "face_description": "sharp jawline, intense green eyes, a scar above one eyebrow",
                "hair": "short, dark, windswept",
                "clothing": "worn leather armor over a dark traveling cloak",
                "body_type": "athletic",
                "personality": "determined, guarded, secretly compassionate",
                "voice": {"tone": "gravelly", "pitch": "low", "pace": "measured", "accent": "neutral"},
                "important_props": ["ancient pendant", "iron shortsword"],
            },
            {
                "name": "Mira",
                "role": "supporting",
                "age": "27",
                "gender": "female",
                "physical_appearance": "tall, graceful posture, pale skin with faint freckles",
                "face_description": "high cheekbones, amber eyes, calm expression",
                "hair": "long auburn hair often tied back",
                "clothing": "practical scholar's robes with a hooded cloak",
                "body_type": "slender",
                "personality": "curious, wise beyond her years, quietly brave",
                "voice": {"tone": "warm", "pitch": "medium", "pace": "measured", "accent": "neutral"},
                "important_props": ["leather-bound journal"],
            },
        ]
    }


def _mock_scenes(user_prompt: str) -> dict:
    return {
        "scenes": [
            {
                "title": "The Ordinary World",
                "location": "a quiet mountain village",
                "time_of_day": "morning",
                "action": "The hero goes about a routine day, unaware of what's coming.",
                "narration": "Before the legend, there was just a young warrior and a quiet village.",
                "dialogue": [],
                "camera_movement": "pan_right",
                "shot_type": "wide",
                "lighting": "soft morning light",
                "visual_style": "cinematic, warm color grade",
                "audio_mood": "peaceful",
            },
            {
                "title": "The Discovery",
                "location": "a hidden cave entrance beneath the mountain",
                "time_of_day": "afternoon",
                "action": "The hero discovers a mysterious ancient entrance carved into stone.",
                "narration": "What they found beneath the mountain would change everything.",
                "dialogue": [
                    {"character_name": "Kael", "text": "This wasn't here before.", "emotion": "wary"}
                ],
                "camera_movement": "dolly_in",
                "shot_type": "medium",
                "lighting": "dim, shafts of light through rock",
                "visual_style": "cinematic, cool color grade, mysterious atmosphere",
                "audio_mood": "suspense",
            },
            {
                "title": "The Confrontation",
                "location": "the ancient kingdom's throne hall",
                "time_of_day": "night",
                "action": "The hero faces the guardian of the kingdom in a tense standoff.",
                "narration": "Here, at last, the warrior would be tested.",
                "dialogue": [
                    {"character_name": "Kael", "text": "I'm not leaving without answers.", "emotion": "resolute"}
                ],
                "camera_movement": "tracking",
                "shot_type": "close_up",
                "lighting": "dramatic torchlight",
                "visual_style": "cinematic, high contrast",
                "audio_mood": "energetic",
            },
            {
                "title": "Resolution",
                "location": "the mountain peak at dawn",
                "time_of_day": "dawn",
                "action": "The hero looks out over the world, forever changed by the journey.",
                "narration": "The kingdom was gone, but its story would live on through them.",
                "dialogue": [],
                "camera_movement": "crane",
                "shot_type": "wide",
                "lighting": "golden dawn light",
                "visual_style": "cinematic, warm color grade",
                "audio_mood": "triumphant",
            },
        ]
    }
