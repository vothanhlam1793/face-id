from __future__ import annotations

import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

BASE_DIR = Path(__file__).resolve().parent.parent


def _path_from_env(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name, str(default)).strip()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


DB_PATH = _path_from_env("FACE_ID_DB_PATH", BASE_DIR / "face_id.db")
MODEL_PATH = BASE_DIR / "models/yolov8n-face.pt"
MODEL_URL = "https://github.com/YapaLab/yolo-face/releases/download/1.0.0/yolov8n-face.pt"
SNAPSHOT_DIR = _path_from_env("FACE_ID_SNAPSHOT_DIR", BASE_DIR / "snapshots")
PEOPLE_DIR = _path_from_env("FACE_ID_PEOPLE_DIR", BASE_DIR / "people")
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STORAGE_BACKEND = os.environ.get("FACE_ID_STORAGE_BACKEND", "local").strip().lower() or "local"
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "").strip().rstrip("/")
NEXTCLOUD_USERNAME = os.environ.get("NEXTCLOUD_USERNAME", "").strip()
NEXTCLOUD_PASSWORD = os.environ.get("NEXTCLOUD_PASSWORD", "").strip()
NEXTCLOUD_ROOT = os.environ.get("NEXTCLOUD_ROOT", "face-id").strip("/") or "face-id"

MATCH_THRESHOLD_HIGH = 0.82
MATCH_THRESHOLD_SUGGEST = 0.72
IMPORT_GROUP_MERGE_THRESHOLD = 0.80
SEEN_UPDATE_INTERVAL_SECONDS = 5
JPEG_QUALITY = 80
TRACK_TTL_SECONDS = 2.5
TRACK_IOU_THRESHOLD = 0.35
TRACK_SAMPLE_INTERVAL_SECONDS = 0.6
GROUP_SAMPLE_LIMIT = 6
MAX_ACTIVE_TRACKS = 24
VIDEO_IMPORT_FRAME_STEP = 12
