from __future__ import annotations

from app.config import BASE_DIR, NEXTCLOUD_PASSWORD, NEXTCLOUD_ROOT, NEXTCLOUD_URL, NEXTCLOUD_USERNAME, STORAGE_BACKEND
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.nextcloud import NextcloudStorageBackend


def create_storage() -> StorageBackend:
    if STORAGE_BACKEND == "nextcloud":
        return NextcloudStorageBackend(
            base_url=NEXTCLOUD_URL,
            username=NEXTCLOUD_USERNAME,
            password=NEXTCLOUD_PASSWORD,
            root=NEXTCLOUD_ROOT,
        )
    return LocalStorageBackend(BASE_DIR)
