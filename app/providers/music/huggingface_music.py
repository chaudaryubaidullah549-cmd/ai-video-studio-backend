"""
Hugging Face Inference Providers - music/SFX adapter.

DOCUMENTED LIMITATION: as of the current Inference Providers task catalog
(https://huggingface.co/docs/inference-providers/en/tasks/index), there
is no `text-to-music` / `text-to-audio` task exposed through Inference
Providers - models like MusicGen are only documented for use via the
`transformers` library or dedicated Inference Endpoints, not the
serverless Inference Providers router this backend targets for
MOCK_MODE-free "free-first" operation.

Rather than fabricate an endpoint, this adapter implements the
MusicProvider/SoundEffectProvider interface and raises a clear,
actionable error. Swap in a real implementation (e.g. a dedicated
Inference Endpoint running MusicGen, or a different music API) by
replacing this class - no other code needs to change, since
services/music_service.py only depends on the MusicProvider interface.
"""
from __future__ import annotations

from app.providers.base import MusicProvider, SoundEffectProvider
from app.models.generation import ProviderGenerationResult
from app.utils.errors import MusicProviderError


_LIMITATION_MESSAGE = (
    "No text-to-music task is currently documented in Hugging Face's "
    "Inference Providers catalog. Configure a dedicated Inference "
    "Endpoint (e.g. running MusicGen) or another music API and implement "
    "a new MusicProvider, or run with MOCK_MODE=true / a procedural "
    "music provider in the meantime."
)


class HuggingFaceMusicProvider(MusicProvider):
    async def generate_music(self, *, mood: str, duration_seconds: float, style: str = "cinematic") -> ProviderGenerationResult:
        raise MusicProviderError(_LIMITATION_MESSAGE, retryable=False)

    async def download_result(self, task_id: str, destination_path: str) -> str:
        raise MusicProviderError(_LIMITATION_MESSAGE, retryable=False)


class HuggingFaceSoundEffectProvider(SoundEffectProvider):
    async def generate_sfx(self, *, description: str, duration_seconds: float) -> ProviderGenerationResult:
        raise MusicProviderError(_LIMITATION_MESSAGE, retryable=False)

    async def download_result(self, task_id: str, destination_path: str) -> str:
        raise MusicProviderError(_LIMITATION_MESSAGE, retryable=False)
