"""
Hugging Face Inference Providers - chat completion LLM adapter.

Uses the documented OpenAI-compatible chat completions route exposed by
the HF Inference Providers router (https://router.huggingface.co), as
described at:
  https://huggingface.co/docs/inference-providers/en/tasks/chat-completion

We call the router directly over HTTPX (rather than the huggingface_hub
SDK) since chat completion is a stable, documented OpenAI-compatible REST
endpoint: POST https://router.huggingface.co/v1/chat/completions
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.utils.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.utils.logging import get_logger, log_event
from app.providers.base import LLMProvider

logger = get_logger(__name__)
settings = get_settings()

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"


class HuggingFaceLLMProvider(LLMProvider):
    def __init__(self, token: str | None = None, model: str | None = None):
        self.token = token or settings.HF_TOKEN
        self.model = model or settings.HF_LLM_MODEL
        if not self.token:
            raise ProviderAuthError(
                "HF_TOKEN is not configured. Set it in the environment or enable MOCK_MODE."
            )

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        max_tokens: int = 2000,
        temperature: float = 0.8,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            # Documented structured-output mode for chat completion, see
            # https://huggingface.co/docs/inference-providers/en/guides/structured-output
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.token}"}

        log_event(logger, "info", "provider.llm.request", model=self.model, json_mode=json_mode)

        try:
            async with httpx.AsyncClient(timeout=settings.PROVIDER_TIMEOUT_SECONDS) as client:
                resp = await client.post(ROUTER_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError("Hugging Face LLM request timed out") from e
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Hugging Face LLM request failed: {e}") from e

        if resp.status_code == 401:
            raise ProviderAuthError("Hugging Face authentication failed. Check HF_TOKEN.")
        if resp.status_code == 429:
            raise ProviderRateLimitError("Hugging Face rate limit exceeded.")
        if resp.status_code >= 500:
            raise ProviderUnavailableError(
                f"Hugging Face LLM provider returned {resp.status_code}"
            )
        if resp.status_code >= 400:
            raise ProviderUnavailableError(
                f"Hugging Face LLM request rejected: {resp.status_code} {resp.text[:300]}"
            )

        data = resp.json()
        log_event(logger, "info", "provider.llm.response", model=self.model, status=resp.status_code)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ProviderUnavailableError("Unexpected response shape from HF chat completion") from e
