"""
Central application configuration.

All configuration is loaded from environment variables (optionally via a
.env file for local development). Nothing in this module should ever be
sent to the frontend - see app/api/* for what is actually exposed.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "AI Video Studio Backend"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)

    # MOCK_MODE=true runs the entire pipeline with no external API calls.
    MOCK_MODE: bool = Field(default=True)

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS ---
    # Comma separated list of allowed origins. The Lovable frontend origin(s)
    # should be added here in production. "*" is only acceptable in DEBUG.
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:5173")

    # --- Database ---
    # SQLite for development. Swap for a Postgres DSN in production - the
    # repository layer uses SQLAlchemy so no application code needs to change.
    DATABASE_URL: str = Field(default=f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")

    # --- Storage ---
    STORAGE_BACKEND: str = Field(default="local")  # local | s3 (future)
    LOCAL_STORAGE_PATH: str = Field(default=str(BASE_DIR / "storage"))
    PUBLIC_BASE_URL: str = Field(default="http://localhost:8000")

    # --- Hugging Face Inference Providers ---
    HF_TOKEN: str = Field(default="")
    # Recommended default per HF Inference Providers docs (Aug 2026):
    # tencent/HunyuanVideo or Lightricks/LTX-Video-0.9.8-13B-distilled (fast).
    HF_VIDEO_MODEL: str = Field(default="Lightricks/LTX-Video-0.9.8-13B-distilled")
    # "auto" lets HF pick the first available provider for the model.
    HF_PROVIDER: str = Field(default="auto")
    HF_LLM_MODEL: str = Field(default="meta-llama/Llama-3.3-70B-Instruct")
    HF_TTS_MODEL: str = Field(default="")  # optional, provider-dependent

    # --- Other provider keys (all optional, all env-based) ---
    OPENAI_API_KEY: str = Field(default="")  # optional alternate LLM provider
    ELEVENLABS_API_KEY: str = Field(default="")  # optional voice provider

    # --- Generation limits / behavior ---
    MAX_PROJECT_DURATION_SECONDS: int = Field(default=180)
    MAX_SCENE_DURATION_SECONDS: int = Field(default=8)
    DEFAULT_SCENE_DURATION_SECONDS: int = Field(default=5)
    PROVIDER_MAX_RETRIES: int = Field(default=3)
    PROVIDER_TIMEOUT_SECONDS: int = Field(default=120)
    PROVIDER_POLL_INTERVAL_SECONDS: float = Field(default=3.0)

    # --- Security / request limits ---
    MAX_REQUEST_BODY_BYTES: int = Field(default=2 * 1024 * 1024)  # 2 MB
    RATE_LIMIT_REQUESTS: int = Field(default=60)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    # --- FFmpeg ---
    FFMPEG_BINARY: str = Field(default="ffmpeg")
    FFPROBE_BINARY: str = Field(default="ffprobe")

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Ensure required directories exist.
    Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings
