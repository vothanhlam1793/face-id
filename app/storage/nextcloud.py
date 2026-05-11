from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import cv2
import numpy as np

from app.storage.base import StorageBackend


class NextcloudStorageBackend(StorageBackend):
    def __init__(self, base_url: str, username: str, password: str, root: str) -> None:
        if not base_url or not username or not password:
            raise ValueError("Nextcloud storage requires URL, username, and password")
        self.base_url = base_url.rstrip("/")
        self.root = root.strip("/")
        self.webdav_root = f"{self.base_url}/remote.php/dav/files/{quote(username)}/{self.root}"
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self.auth_header = {"Authorization": f"Basic {token}"}
        self._ensure_dir("")

    def _url(self, relative_path: str) -> str:
        parts = [quote(part) for part in PurePosixPath(relative_path).parts if part not in {".", ""}]
        suffix = "/".join(parts)
        return self.webdav_root if not suffix else f"{self.webdav_root}/{suffix}"

    def _request(self, method: str, relative_path: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes | None:
        request_headers = dict(self.auth_header)
        if headers:
            request_headers.update(headers)
        request = Request(self._url(relative_path), data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                return None
            if error.code not in {201, 204, 207, 405}:
                raise
            return error.read()
        except URLError as error:
            raise RuntimeError(f"Nextcloud request failed: {error}") from error

    def _ensure_dir(self, relative_dir: str) -> None:
        if not relative_dir:
            self._request("MKCOL", "")
            return
        current = PurePosixPath("")
        for part in PurePosixPath(relative_dir).parts:
            if part in {".", ""}:
                continue
            current = current / part
            self._request("MKCOL", current.as_posix())

    def save_image(self, relative_path: str, image: np.ndarray) -> str:
        success, encoded = cv2.imencode(PurePosixPath(relative_path).suffix or ".jpg", image)
        if not success:
            raise RuntimeError("Failed to encode image")
        self._ensure_dir(PurePosixPath(relative_path).parent.as_posix())
        self._request("PUT", relative_path, data=encoded.tobytes(), headers={"Content-Type": "image/jpeg"})
        return relative_path

    def move_file(self, old_relative_path: str, new_relative_path: str) -> str:
        self._ensure_dir(PurePosixPath(new_relative_path).parent.as_posix())
        self._request("MOVE", old_relative_path, headers={"Destination": self._url(new_relative_path), "Overwrite": "F"})
        return new_relative_path

    def file_exists(self, relative_path: str) -> bool:
        return self._request("HEAD", relative_path) is not None

    def read_bytes(self, relative_path: str) -> bytes | None:
        return self._request("GET", relative_path)

    def read_image(self, relative_path: str) -> np.ndarray | None:
        content = self.read_bytes(relative_path)
        if content is None:
            return None
        return cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)

    def list_files(self, relative_dir: str) -> list[str]:
        body = self._request("PROPFIND", relative_dir, headers={"Depth": "1"})
        if body is None:
            return []
        root = ET.fromstring(body)
        namespace = {"d": "DAV:"}
        current_name = PurePosixPath(relative_dir).name
        files: list[str] = []
        for href in root.findall("d:response/d:href", namespace):
            name = PurePosixPath(href.text or "").name
            if not name or name == current_name:
                continue
            files.append(f"{relative_dir}/{name}".strip("/"))
        return sorted(files)

    def public_url(self, relative_path: str) -> str:
        return f"/media/{relative_path}"
