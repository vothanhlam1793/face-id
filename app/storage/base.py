from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class StorageBackend(ABC):
    @abstractmethod
    def save_image(self, relative_path: str, image: np.ndarray) -> str: ...

    @abstractmethod
    def move_file(self, old_relative_path: str, new_relative_path: str) -> str: ...

    @abstractmethod
    def file_exists(self, relative_path: str) -> bool: ...

    @abstractmethod
    def read_bytes(self, relative_path: str) -> bytes | None: ...

    @abstractmethod
    def read_image(self, relative_path: str) -> np.ndarray | None: ...

    @abstractmethod
    def list_files(self, relative_dir: str) -> list[str]: ...

    @abstractmethod
    def public_url(self, relative_path: str) -> str: ...
