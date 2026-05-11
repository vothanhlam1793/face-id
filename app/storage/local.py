from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _absolute(self, relative_path: str) -> Path:
        return self.base_dir / relative_path

    def save_image(self, relative_path: str, image: np.ndarray) -> str:
        absolute = self._absolute(relative_path)
        absolute.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(absolute), image)
        return relative_path

    def move_file(self, old_relative_path: str, new_relative_path: str) -> str:
        old_absolute = self._absolute(old_relative_path)
        new_absolute = self._absolute(new_relative_path)
        new_absolute.parent.mkdir(parents=True, exist_ok=True)
        if old_absolute.exists():
            old_absolute.replace(new_absolute)
        return new_relative_path

    def file_exists(self, relative_path: str) -> bool:
        return self._absolute(relative_path).exists()

    def read_bytes(self, relative_path: str) -> bytes | None:
        absolute = self._absolute(relative_path)
        if not absolute.exists():
            return None
        return absolute.read_bytes()

    def read_image(self, relative_path: str) -> np.ndarray | None:
        absolute = self._absolute(relative_path)
        if not absolute.exists():
            return None
        return cv2.imread(str(absolute), cv2.IMREAD_COLOR)

    def list_files(self, relative_dir: str) -> list[str]:
        absolute = self._absolute(relative_dir)
        if not absolute.exists():
            return []
        return sorted([f"{relative_dir}/{path.name}".strip("/") for path in absolute.iterdir() if path.is_file()])

    def public_url(self, relative_path: str) -> str:
        return f"/media/{relative_path}"
