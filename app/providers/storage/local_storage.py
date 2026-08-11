from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_settings
from app.providers.base import StorageProvider
from app.utils.errors import StorageError

settings = get_settings()


class LocalStorageProvider(StorageProvider):
    """Development storage backend: writes under LOCAL_STORAGE_PATH and
    serves files via the /media static mount configured in app/main.py.

    To move to production object storage, implement a new StorageProvider
    (e.g. S3StorageProvider) with the same interface and switch it in
    providers/storage/__init__.py based on settings.STORAGE_BACKEND.
    """

    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        # Prevent path traversal outside the storage root.
        candidate = (self.base_path / relative_path).resolve()
        if not str(candidate).startswith(str(self.base_path.resolve())):
            raise StorageError("Invalid storage path", details={"path": relative_path})
        return candidate

    def save_file(self, *, relative_path: str, content: bytes) -> str:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(content)
        except OSError as e:
            raise StorageError(f"Failed to write file: {e}") from e
        return self.url_for(relative_path)

    def save_file_from_path(self, *, relative_path: str, source_path: str) -> str:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source_path, path)
        except OSError as e:
            raise StorageError(f"Failed to copy file: {e}") from e
        return self.url_for(relative_path)

    def get_absolute_path(self, relative_path: str) -> str:
        return str(self._resolve(relative_path))

    def url_for(self, relative_path: str) -> str:
        clean = relative_path.replace("\\", "/").lstrip("/")
        return f"{settings.PUBLIC_BASE_URL}/media/{clean}"

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).exists()

    def local_path_for_url(self, url: str) -> str:
        prefix = f"{settings.PUBLIC_BASE_URL}/media/"
        if not url.startswith(prefix):
            raise StorageError(f"URL is not a local media URL: {url}")
        relative_path = url[len(prefix):]
        return self.get_absolute_path(relative_path)
