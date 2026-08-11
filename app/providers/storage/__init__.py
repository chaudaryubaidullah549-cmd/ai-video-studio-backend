from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import StorageProvider
from app.providers.storage.local_storage import LocalStorageProvider

settings = get_settings()


@lru_cache
def get_storage_provider() -> StorageProvider:
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageProvider()
    raise NotImplementedError(
        f"Storage backend '{settings.STORAGE_BACKEND}' is not implemented. "
        "Add a new StorageProvider subclass and register it here."
    )
