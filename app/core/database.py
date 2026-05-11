from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

import numpy as np

from app.config import DB_PATH, GROUP_SAMPLE_LIMIT


class FaceDatabase:
    def __init__(self, db_path=DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _table_columns(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}

    def _init_db(self) -> None:
        with self._connect() as connection:
            people_columns = self._table_columns(connection, "people")
            if people_columns and "cover_snapshot_path" not in people_columns:
                connection.execute("DROP TABLE IF EXISTS face_samples")
                connection.execute("DROP TABLE IF EXISTS unknown_group_samples")
                connection.execute("DROP TABLE IF EXISTS unknown_groups")
                connection.execute("DROP TABLE IF EXISTS pending_faces")
                connection.execute("DROP TABLE IF EXISTS people")

            connection.execute(
                "CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, cover_snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL, last_seen TEXT, seen_count INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS face_samples (id TEXT PRIMARY KEY, person_id TEXT NOT NULL, embedding TEXT NOT NULL, snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(person_id) REFERENCES people(id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS unknown_groups (id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, status TEXT NOT NULL, cover_snapshot_path TEXT NOT NULL, suggested_person_id TEXT, suggested_person_name TEXT, suggested_score REAL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS unknown_group_samples (id TEXT PRIMARY KEY, group_id TEXT NOT NULL, embedding TEXT NOT NULL, snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL, quality_score REAL NOT NULL, FOREIGN KEY(group_id) REFERENCES unknown_groups(id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return str(row[0])

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
                connection.commit()

    def get_people(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT p.*, COUNT(fs.id) AS sample_count FROM people p LEFT JOIN face_samples fs ON fs.person_id = p.id GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_samples(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fs.*, p.name AS person_name FROM face_samples fs JOIN people p ON p.id = fs.person_id"
            ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["embedding"] = np.array(json.loads(item["embedding"]), dtype=np.float32)
        return items

    def get_person(self, person_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        return dict(row) if row else None

    def get_pending_group_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM unknown_groups WHERE status = 'pending'").fetchone()
        return int(row[0])

    def get_unknown_groups(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            groups = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM unknown_groups WHERE status = 'pending' ORDER BY updated_at DESC"
                ).fetchall()
            ]
            for group in groups:
                samples = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT id, snapshot_path, quality_score, created_at FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC",
                        (group["id"],),
                    ).fetchall()
                ]
                group["samples"] = samples
                group["sample_count"] = len(samples)
        return groups

    def get_unknown_group_sample_embeddings(self, group_id: str) -> list[np.ndarray]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT embedding FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC",
                (group_id,),
            ).fetchall()
        return [np.array(json.loads(row[0]), dtype=np.float32) for row in rows]

    def create_unknown_group(self, group_id: str, label: str, cover_snapshot_path: str, created_at: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO unknown_groups (id, label, created_at, updated_at, status, cover_snapshot_path, suggested_person_id, suggested_person_name, suggested_score) VALUES (?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL)",
                    (group_id, label, created_at, created_at, cover_snapshot_path),
                )
                connection.commit()

    def add_unknown_group_sample(self, group_id: str, embedding: list[float], snapshot_path: str, created_at: str, quality_score: float, update_cover: bool) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO unknown_group_samples (id, group_id, embedding, snapshot_path, created_at, quality_score) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), group_id, json.dumps(embedding), snapshot_path, created_at, quality_score),
                )
                if update_cover:
                    connection.execute(
                        "UPDATE unknown_groups SET cover_snapshot_path = ?, updated_at = ? WHERE id = ?",
                        (snapshot_path, created_at, group_id),
                    )
                else:
                    connection.execute(
                        "UPDATE unknown_groups SET updated_at = ? WHERE id = ?",
                        (created_at, group_id),
                    )

                sample_ids = [
                    row[0]
                    for row in connection.execute(
                        "SELECT id FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC",
                        (group_id,),
                    ).fetchall()
                ]
                for stale_id in sample_ids[GROUP_SAMPLE_LIMIT:]:
                    connection.execute("DELETE FROM unknown_group_samples WHERE id = ?", (stale_id,))
                connection.commit()

    def update_group_suggestion(self, group_id: str, suggestion: dict[str, Any] | None) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE unknown_groups SET suggested_person_id = ?, suggested_person_name = ?, suggested_score = ? WHERE id = ?",
                    (
                        suggestion.get("person_id") if suggestion else None,
                        suggestion.get("person_name") if suggestion else None,
                        suggestion.get("score") if suggestion else None,
                        group_id,
                    ),
                )
                connection.commit()

    def merge_unknown_group_into(self, source_group_id: str, target_group_id: str) -> None:
        if source_group_id == target_group_id:
            return
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE unknown_group_samples SET group_id = ? WHERE group_id = ?",
                    (target_group_id, source_group_id),
                )
                cover_row = connection.execute(
                    "SELECT snapshot_path, created_at FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC LIMIT 1",
                    (target_group_id,),
                ).fetchone()
                if cover_row:
                    connection.execute(
                        "UPDATE unknown_groups SET cover_snapshot_path = ?, updated_at = ? WHERE id = ?",
                        (cover_row[0], cover_row[1], target_group_id),
                    )
                connection.execute(
                    "UPDATE unknown_groups SET status = 'merged', updated_at = ? WHERE id = ?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), source_group_id),
                )
                connection.commit()

    def get_group_sample_payload(self, group_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT embedding, snapshot_path, created_at FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC",
                (group_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_unknown_group(self, group_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM unknown_groups WHERE id = ?", (group_id,)).fetchone()
        return dict(row) if row else None

    def delete_group_sample(self, group_id: str, sample_id: str) -> None:
        with self.lock:
            with self._connect() as connection:
                count_row = connection.execute(
                    "SELECT COUNT(*) FROM unknown_group_samples WHERE group_id = ?",
                    (group_id,),
                ).fetchone()
                if not count_row or int(count_row[0]) <= 1:
                    raise ValueError("Group phai giu it nhat 1 anh")
                connection.execute(
                    "DELETE FROM unknown_group_samples WHERE id = ? AND group_id = ?",
                    (sample_id, group_id),
                )
                cover_row = connection.execute(
                    "SELECT snapshot_path FROM unknown_group_samples WHERE group_id = ? ORDER BY quality_score DESC, created_at ASC LIMIT 1",
                    (group_id,),
                ).fetchone()
                if cover_row:
                    connection.execute(
                        "UPDATE unknown_groups SET cover_snapshot_path = ?, updated_at = ? WHERE id = ?",
                        (cover_row[0], time.strftime("%Y-%m-%d %H:%M:%S"), group_id),
                    )
                connection.commit()

    def resolve_group(self, group_id: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE unknown_groups SET status = 'resolved', updated_at = ? WHERE id = ?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), group_id),
                )
                connection.commit()

    def dismiss_group(self, group_id: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE unknown_groups SET status = 'dismissed', updated_at = ? WHERE id = ?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), group_id),
                )
                connection.commit()

    def create_person_with_samples(self, name: str, samples: list[dict[str, Any]], cover_snapshot_path: str, created_at: str) -> None:
        with self.lock:
            person_id = str(uuid.uuid4())
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO people (id, name, cover_snapshot_path, created_at, last_seen, seen_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (person_id, name, cover_snapshot_path, created_at, created_at, len(samples)),
                )
                for sample in samples:
                    connection.execute(
                        "INSERT INTO face_samples (id, person_id, embedding, snapshot_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), person_id, sample["embedding"], sample["snapshot_path"], sample["created_at"]),
                    )
                connection.commit()

    def create_person_with_samples_returning_id(self, name: str, samples: list[dict[str, Any]], cover_snapshot_path: str, created_at: str) -> str:
        person_id = str(uuid.uuid4())
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO people (id, name, cover_snapshot_path, created_at, last_seen, seen_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (person_id, name, cover_snapshot_path, created_at, created_at, len(samples)),
                )
                for sample in samples:
                    connection.execute(
                        "INSERT INTO face_samples (id, person_id, embedding, snapshot_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), person_id, sample["embedding"], sample["snapshot_path"], sample["created_at"]),
                    )
                connection.commit()
        return person_id

    def attach_samples_to_person(self, person_id: str, samples: list[dict[str, Any]]) -> None:
        with self.lock:
            with self._connect() as connection:
                for sample in samples:
                    connection.execute(
                        "INSERT INTO face_samples (id, person_id, embedding, snapshot_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), person_id, sample["embedding"], sample["snapshot_path"], sample["created_at"]),
                    )
                connection.execute(
                    "UPDATE people SET last_seen = ?, seen_count = seen_count + ? WHERE id = ?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), len(samples), person_id),
                )
                connection.commit()

    def replace_person_samples(self, person_id: str, samples: list[dict[str, Any]], cover_snapshot_path: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute("DELETE FROM face_samples WHERE person_id = ?", (person_id,))
                for sample in samples:
                    connection.execute(
                        "INSERT INTO face_samples (id, person_id, embedding, snapshot_path, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), person_id, sample["embedding"], sample["snapshot_path"], sample["created_at"]),
                    )
                connection.execute(
                    "UPDATE people SET cover_snapshot_path = ? WHERE id = ?",
                    (cover_snapshot_path, person_id),
                )
                connection.commit()

    def update_person_cover_snapshot(self, person_id: str, cover_snapshot_path: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE people SET cover_snapshot_path = ? WHERE id = ?",
                    (cover_snapshot_path, person_id),
                )
                connection.commit()

    def update_sample_snapshot_path(self, old_snapshot_path: str, new_snapshot_path: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE face_samples SET snapshot_path = ? WHERE snapshot_path = ?",
                    (new_snapshot_path, old_snapshot_path),
                )
                connection.execute(
                    "UPDATE people SET cover_snapshot_path = ? WHERE cover_snapshot_path = ?",
                    (new_snapshot_path, old_snapshot_path),
                )
                connection.commit()

    def update_seen(self, person_id: str, seen_at: str) -> None:
        with self.lock:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE people SET last_seen = ?, seen_count = seen_count + 1 WHERE id = ?",
                    (seen_at, person_id),
                )
                connection.commit()
