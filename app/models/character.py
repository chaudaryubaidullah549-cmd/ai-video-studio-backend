from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class VoiceCharacteristics(BaseModel):
    tone: str = Field(default="neutral", description="e.g. warm, gravelly, bright")
    pitch: str = Field(default="medium", description="low | medium | high")
    pace: str = Field(default="medium", description="slow | medium | fast")
    accent: Optional[str] = None


class Character(BaseModel):
    """A single entry in the project's Character Bible.

    Every scene prompt that includes this character MUST reuse this same
    description verbatim (or a deterministic templated form of it) so the
    video provider receives a consistent visual description across shots.
    This does not guarantee pixel-level consistency - see
    `VideoProvider` docstring for why - but it is the best lever we have
    with text/image-conditioned video models.
    """

    id: str
    name: str
    role: str = Field(default="supporting", description="protagonist | antagonist | supporting")
    age: Optional[str] = None
    gender: Optional[str] = None
    physical_appearance: str = ""
    face_description: str = ""
    hair: str = ""
    clothing: str = ""
    body_type: str = ""
    personality: str = ""
    voice: VoiceCharacteristics = Field(default_factory=VoiceCharacteristics)
    important_props: List[str] = Field(default_factory=list)
    # Optional reference image path/URL for image-to-video conditioning.
    # Populated later when a reference-image generation step is enabled.
    reference_image_url: Optional[str] = None

    def visual_descriptor(self) -> str:
        """Deterministic, reusable text descriptor for prompt-building.

        Keeping this in one place guarantees every scene/shot prompt that
        calls this method gets an identical string for the same character.
        """
        parts = [self.name]
        if self.age:
            parts.append(f"{self.age} years old")
        if self.gender:
            parts.append(self.gender)
        if self.body_type:
            parts.append(f"{self.body_type} build")
        if self.face_description:
            parts.append(f"face: {self.face_description}")
        if self.hair:
            parts.append(f"hair: {self.hair}")
        if self.clothing:
            parts.append(f"wearing {self.clothing}")
        if self.physical_appearance:
            parts.append(self.physical_appearance)
        return ", ".join(p for p in parts if p)
