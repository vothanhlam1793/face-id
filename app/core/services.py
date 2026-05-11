from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import HTTPException
from pillow_heif import read_heif

from app.config import (
    GROUP_SAMPLE_LIMIT,
    IMPORT_GROUP_MERGE_THRESHOLD,
    JPEG_QUALITY,
    MATCH_THRESHOLD_HIGH,
    MATCH_THRESHOLD_SUGGEST,
    MODEL_PATH,
    MODEL_URL,
    PEOPLE_DIR,
    SEEN_UPDATE_INTERVAL_SECONDS,
    SNAPSHOT_DIR,
    TRACK_SAMPLE_INTERVAL_SECONDS,
)
from app.core.database import FaceDatabase
from app.core.models import MatchResult, TrackState
from app.storage import create_storage
from app.vision.detector import FaceDetector
from app.vision.embedder import FaceEmbedder
from app.vision.recognizer import FaceRecognizer
from app.vision.tracker import SimpleFaceTracker


class FaceIDService:
    def __init__(self) -> None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Missing model at {MODEL_PATH}. Download it from {MODEL_URL}.")

        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
        self.storage = create_storage()
        self.database = FaceDatabase()
        self.detector = FaceDetector(str(MODEL_PATH))
        self.embedder = FaceEmbedder()
        self.recognizer = FaceRecognizer(self.database)
        self.tracker = SimpleFaceTracker()

        self.frame_lock = threading.Lock()
        self.latest_frame: bytes | None = None
        self.latest_raw_frame: np.ndarray | None = None
        self.last_seen_updates: dict[str, float] = {}
        self.worker: threading.Thread | None = None
        self.capture: cv2.VideoCapture | None = None
        self.camera_source_type = "webcam"
        self.camera_source_value = "0"
        self.camera_label = "Webcam 0"
        self.camera_enabled = False
        self.camera_connected = False
        self.camera_ready = False
        self.status_line = "Chua bat camera. Hay chon webcam hoac nhap link RTSP."
        self._load_camera_settings()

    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _save_snapshot(self, frame: np.ndarray, sample_id: str) -> str:
        name = f"{sample_id}.jpg"
        return self.storage.save_image(f"snapshots/{name}", frame)

    def _slugify_name(self, name: str) -> str:
        allowed = [char.lower() if char.isalnum() else "-" for char in name.strip()]
        slug = "".join(allowed)
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-") or f"person-{uuid.uuid4().hex[:8]}"

    def _person_dir(self, person_id: str, person_name: str) -> str:
        return f"people/{self._slugify_name(person_name)}-{person_id[:8]}"

    def _move_group_samples_to_person_dir(self, person_id: str, person_name: str, samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        person_dir = self._person_dir(person_id, person_name)

        moved_samples: list[dict[str, Any]] = []
        cover_snapshot_path = ""
        for index, sample in enumerate(samples, start=1):
            old_relative = sample["snapshot_path"]
            suffix = Path(old_relative).suffix or ".jpg"
            new_name = f"sample-{index:03d}{suffix}"
            new_relative = f"{person_dir}/{new_name}"
            counter = 1
            while self.storage.file_exists(new_relative):
                new_relative = f"{person_dir}/sample-{index:03d}-{counter}{suffix}"
                counter += 1
            if self.storage.file_exists(old_relative):
                self.storage.move_file(old_relative, new_relative)
            moved_sample = dict(sample)
            moved_sample["snapshot_path"] = new_relative
            moved_samples.append(moved_sample)
            if index == 1:
                cover_snapshot_path = new_relative

        return moved_samples, cover_snapshot_path

    def _load_face_from_saved_image(self, snapshot_path: str) -> np.ndarray | None:
        return self.storage.read_image(snapshot_path)

    def _decode_uploaded_image(self, content: bytes) -> np.ndarray | None:
        image_array = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is not None:
            return image

        try:
            heif = read_heif(content)
        except Exception:
            return None

        rgb = np.asarray(heif.to_pillow())
        if rgb.ndim == 2:
            return cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
        if rgb.shape[2] == 4:
            return cv2.cvtColor(rgb, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _is_video_file(self, filename: str) -> bool:
        return filename.lower().endswith((".mp4", ".mov", ".m4v", ".avi"))

    def _process_detected_faces_from_frame(self, image: np.ndarray, label_prefix: str) -> int:
        detected_faces = 0
        boxes = self.detector.detect(image)
        for raw_box in boxes:
            x1, y1, x2, y2 = raw_box
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            face = image[y1:y2, x1:x2]
            if face.size == 0 or min(face.shape[:2]) < 40:
                continue

            detected_faces += 1
            self._create_group_from_face(face, label_prefix=label_prefix)
        return detected_faces

    def _process_video_frame_with_tracker(
        self,
        image: np.ndarray,
        tracker: SimpleFaceTracker,
        timeline_now: float,
        label_prefix: str,
    ) -> int:
        detected_faces = 0
        for raw_box in self.detector.detect(image):
            x1, y1, x2, y2 = raw_box
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            box = (x1, y1, x2, y2)
            face = image[y1:y2, x1:x2]
            if face.size == 0 or min(face.shape[:2]) < 40:
                continue

            detected_faces += 1
            track = tracker.match_or_create(box, now=timeline_now)
            embedding = self.embedder.compute(face)
            match = self.recognizer.best_match(embedding)
            if match and match.score >= MATCH_THRESHOLD_HIGH:
                track.recognized_person_id = match.person_id
                continue

            track = self._ensure_unknown_track(track, face, embedding, label_prefix=label_prefix)
            self._register_unknown_sample(track, face, embedding, now=timeline_now)

        return detected_faces

    def _import_video_file(self, filename: str, content: bytes) -> tuple[int, int]:
        frames_scanned = 0
        detected_faces = 0
        tracker = SimpleFaceTracker()

        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".mp4", delete=True) as temp_file:
            temp_file.write(content)
            temp_file.flush()

            capture = cv2.VideoCapture(temp_file.name)
            if not capture.isOpened():
                return 0, 0

            fps = capture.get(cv2.CAP_PROP_FPS)
            if not fps or fps <= 0:
                fps = 25.0

            frame_index = 0
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    timeline_now = frame_index / fps
                    frames_scanned += 1
                    detected_faces += self._process_video_frame_with_tracker(
                        frame,
                        tracker=tracker,
                        timeline_now=timeline_now,
                        label_prefix=f"Imported {filename}",
                    )
                    frame_index += 1
            finally:
                capture.release()

        return frames_scanned, detected_faces

    def _should_update_seen(self, person_id: str) -> bool:
        now = time.time()
        last = self.last_seen_updates.get(person_id, 0.0)
        if now - last < SEEN_UPDATE_INTERVAL_SECONDS:
            return False
        self.last_seen_updates[person_id] = now
        return True

    def _best_group_suggestion(self, group_id: str) -> MatchResult | None:
        samples = self.database.get_group_sample_payload(group_id)
        return self.recognizer.best_group_suggestion(samples)

    def _group_centroid(self, group_id: str) -> np.ndarray | None:
        embeddings = self.database.get_unknown_group_sample_embeddings(group_id)
        if not embeddings:
            return None
        centroid = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
        norm = np.linalg.norm(centroid)
        return centroid if norm == 0 else centroid / norm

    def _merge_similar_pending_groups(self, threshold: float = IMPORT_GROUP_MERGE_THRESHOLD) -> int:
        groups = self.database.get_unknown_groups()
        centroids: dict[str, np.ndarray] = {}
        for group in groups:
            centroid = self._group_centroid(group["id"])
            if centroid is not None:
                centroids[group["id"]] = centroid

        merged = 0
        visited: set[str] = set()
        for group in groups:
            source_id = group["id"]
            if source_id in visited or source_id not in centroids:
                continue

            for candidate in groups:
                target_id = candidate["id"]
                if target_id == source_id or target_id in visited or target_id not in centroids:
                    continue
                score = float(np.dot(centroids[source_id], centroids[target_id]))
                if score >= threshold:
                    self.database.merge_unknown_group_into(target_id, source_id)
                    visited.add(target_id)
                    merged += 1

            visited.add(source_id)

        return merged

    def _ensure_unknown_track(self, track: TrackState, face_image: np.ndarray, embedding: np.ndarray, label_prefix: str = "Unknown Group") -> TrackState:
        if track.group_id:
            return track

        group_id = str(uuid.uuid4())
        sample_id = str(uuid.uuid4())
        snapshot_path = self._save_snapshot(face_image, sample_id)
        label = f"{label_prefix} {group_id[:8]}"
        created_at = self._timestamp()
        quality_score = float(face_image.shape[0] * face_image.shape[1])

        self.database.create_unknown_group(group_id, label, snapshot_path, created_at)
        self.database.add_unknown_group_sample(group_id, embedding.tolist(), snapshot_path, created_at, quality_score, update_cover=False)

        suggestion = self._best_group_suggestion(group_id)
        self.database.update_group_suggestion(group_id, match_to_dict(suggestion))

        track.group_id = group_id
        track.label = label
        track.sample_count = 1
        track.best_quality = quality_score
        track.last_sample_at = time.time()
        return track

    def _register_unknown_sample(self, track: TrackState, face_image: np.ndarray, embedding: np.ndarray, now: float | None = None) -> str:
        now = time.time() if now is None else now
        if now - track.last_sample_at < TRACK_SAMPLE_INTERVAL_SECONDS:
            return track.label
        if track.sample_count >= GROUP_SAMPLE_LIMIT:
            return track.label

        sample_id = str(uuid.uuid4())
        snapshot_path = self._save_snapshot(face_image, sample_id)
        quality_score = float(face_image.shape[0] * face_image.shape[1])
        update_cover = quality_score > track.best_quality
        self.database.add_unknown_group_sample(
            track.group_id,
            embedding.tolist(),
            snapshot_path,
            self._timestamp(),
            quality_score,
            update_cover,
        )
        track.sample_count += 1
        track.last_sample_at = now
        if update_cover:
            track.best_quality = quality_score

        suggestion = self._best_group_suggestion(track.group_id)
        self.database.update_group_suggestion(track.group_id, match_to_dict(suggestion))
        return track.label

    def _annotate(self, frame: np.ndarray, box: tuple[int, int, int, int], label: str) -> None:
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (124, 156, 255), 2)
        cv2.rectangle(frame, (x1, max(0, y1 - 28)), (x2, y1), (124, 156, 255), -1)
        cv2.putText(frame, label, (x1 + 8, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 17, 31), 2, cv2.LINE_AA)

    def _create_group_from_face(self, face_image: np.ndarray, label_prefix: str = "Imported Group") -> str:
        embedding = self.embedder.compute(face_image)
        group_id = str(uuid.uuid4())
        sample_id = str(uuid.uuid4())
        snapshot_path = self._save_snapshot(face_image, sample_id)
        created_at = self._timestamp()
        quality_score = float(face_image.shape[0] * face_image.shape[1])
        label = f"{label_prefix} {group_id[:8]}"

        self.database.create_unknown_group(group_id, label, snapshot_path, created_at)
        self.database.add_unknown_group_sample(
            group_id,
            embedding.tolist(),
            snapshot_path,
            created_at,
            quality_score,
            update_cover=False,
        )
        suggestion = self._best_group_suggestion(group_id)
        self.database.update_group_suggestion(group_id, match_to_dict(suggestion))
        return group_id

    def _build_capture_target(self) -> int | str:
        if self.camera_source_type == "webcam":
            return int(self.camera_source_value)
        return self.camera_source_value

    def _camera_label_for(self, source_type: str, source_value: str) -> str:
        if source_type == "webcam":
            return f"Webcam {source_value}"
        return "RTSP Stream"

    def _load_camera_settings(self) -> None:
        source_type = self.database.get_setting("camera_source_type", "webcam") or "webcam"
        source_value = self.database.get_setting("camera_source_value", "0") or "0"
        if source_type not in {"webcam", "rtsp"}:
            source_type = "webcam"
            source_value = "0"
        if source_type == "webcam" and not source_value.isdigit():
            source_value = "0"

        self.camera_source_type = source_type
        self.camera_source_value = source_value
        self.camera_label = self._camera_label_for(source_type, source_value)
        self.status_line = f"Da tai cau hinh {self.camera_label}. Nhan Bat camera de khoi dong."

    def _save_camera_settings(self) -> None:
        self.database.set_setting("camera_source_type", self.camera_source_type)
        self.database.set_setting("camera_source_value", self.camera_source_value)

    def _release_capture(self) -> None:
        capture = self.capture
        self.capture = None
        if capture is not None:
            capture.release()

    def _scan_frame(self, frame: np.ndarray) -> tuple[np.ndarray, int, int]:
        scanned_frame = frame.copy()
        detected_faces = 0
        recognized_faces = 0
        for raw_box in self.detector.detect(scanned_frame):
            x1, y1, x2, y2 = raw_box
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(scanned_frame.shape[1], x2)
            y2 = min(scanned_frame.shape[0], y2)
            box = (x1, y1, x2, y2)
            face = scanned_frame[y1:y2, x1:x2]
            if face.size == 0 or min(face.shape[:2]) < 40:
                continue

            detected_faces += 1
            track = self.tracker.match_or_create(box)
            embedding = self.embedder.compute(face)
            match = self.recognizer.best_match(embedding)

            if match and match.score >= MATCH_THRESHOLD_HIGH:
                label = f"{match.person_name} {match.score:.2f}"
                track.recognized_person_id = match.person_id
                recognized_faces += 1
                if self._should_update_seen(match.person_id):
                    self.database.update_seen(match.person_id, self._timestamp())
            else:
                track = self._ensure_unknown_track(track, face, embedding)
                label = self._register_unknown_sample(track, face, embedding)

            self._annotate(scanned_frame, box, label)

        return scanned_frame, detected_faces, recognized_faces

    def list_webcams(self, max_devices: int = 6) -> list[dict[str, str]]:
        ffmpeg_devices = self._ffmpeg_camera_devices()
        webcams: list[dict[str, str]] = []
        misses_in_a_row = 0
        for index in range(max_devices):
            capture = cv2.VideoCapture(index)
            if capture.isOpened():
                label_name = ffmpeg_devices.get(index, f"Webcam {index}")
                label = f"{label_name} ({index})"
                webcams.append({"id": str(index), "label": label})
                misses_in_a_row = 0
            else:
                misses_in_a_row += 1
            capture.release()
            if misses_in_a_row >= 2 and webcams:
                break
        return webcams

    def _ffmpeg_camera_devices(self) -> dict[int, str]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return {}

        devices: dict[int, str] = {}
        in_video_section = False
        output = f"{result.stdout}\n{result.stderr}"
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if "AVFoundation video devices:" in line:
                in_video_section = True
                continue
            if "AVFoundation audio devices:" in line:
                break
            if not in_video_section:
                continue

            match = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if match is None:
                continue
            index = int(match.group(1))
            name = match.group(2).strip()
            if not name or name.lower().startswith("capture screen"):
                continue
            devices[index] = name
        return devices

    def get_camera_devices(self) -> dict[str, Any]:
        return {
            "devices": self.list_webcams(),
            "selected_source_type": self.camera_source_type,
            "selected_source_value": self.camera_source_value,
        }

    def configure_camera(self, source_type: str, source_value: str) -> dict[str, Any]:
        source_type = source_type.strip().lower()
        source_value = source_value.strip()
        if source_type not in {"webcam", "rtsp"}:
            raise HTTPException(status_code=400, detail="Unsupported camera source")
        if source_type == "webcam":
            if not source_value.isdigit():
                raise HTTPException(status_code=400, detail="Webcam id must be numeric")
        else:
            if not source_value:
                raise HTTPException(status_code=400, detail="RTSP link cannot be empty")

        if self.camera_enabled:
            self.stop_camera()

        self.camera_source_type = source_type
        self.camera_source_value = source_value
        self.camera_label = self._camera_label_for(source_type, source_value)
        self._save_camera_settings()
        self.camera_ready = False
        self.camera_connected = False
        self.latest_frame = None
        self.latest_raw_frame = None
        self.status_line = f"Da luu cau hinh nguon {self.camera_label} vao he thong. Nhan Bat camera de khoi dong."
        return self.get_state()

    def start_camera(self) -> dict[str, Any]:
        if self.camera_enabled:
            return self.get_state()

        target = self._build_capture_target()
        self.camera_enabled = True
        self.camera_connected = False
        self.camera_ready = False
        self.latest_frame = None
        self.latest_raw_frame = None
        self.status_line = f"Dang ket noi toi {self.camera_label}..."
        self.capture = cv2.VideoCapture(target)
        if self.capture is None or not self.capture.isOpened():
            self.camera_enabled = False
            self.camera_connected = False
            self.camera_ready = False
            self.status_line = f"Khong ket noi duoc {self.camera_label}. Kiem tra quyen truy cap hoac link RTSP."
            self._release_capture()
            return self.get_state()

        self.camera_connected = True
        self.camera_ready = True
        self.status_line = f"Da ket noi {self.camera_label}. Camera dang hoat dong thanh cong."
        self.worker = threading.Thread(target=self._camera_loop, daemon=True)
        self.worker.start()
        return self.get_state()

    def stop_camera(self) -> dict[str, Any]:
        self.camera_enabled = False
        self.camera_connected = False
        self.camera_ready = False
        self.latest_frame = None
        self.latest_raw_frame = None
        self.status_line = f"Da tat {self.camera_label}."
        self._release_capture()
        return self.get_state()

    def _camera_loop(self) -> None:
        while self.camera_enabled:
            capture = self.capture
            if capture is None:
                break
            ok, frame = capture.read()
            if not ok:
                self.camera_connected = False
                self.camera_ready = False
                self.status_line = f"Mat ket noi {self.camera_label}."
                self._release_capture()
                self.camera_enabled = False
                time.sleep(0.2)
                break

            scanned_frame, detected_faces, recognized_faces = self._scan_frame(frame)
            success, encoded = cv2.imencode(".jpg", scanned_frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if success:
                with self.frame_lock:
                    self.latest_raw_frame = frame.copy()
                    self.latest_frame = encoded.tobytes()
            if detected_faces:
                unknown_faces = max(0, detected_faces - recognized_faces)
                self.status_line = (
                    f"{self.camera_label} dang quet: {detected_faces} khuon mat, "
                    f"{recognized_faces} da nhan dien, {unknown_faces} unknown."
                )
            else:
                self.status_line = f"{self.camera_label} dang hoat dong. Chua thay khuon mat nao."
        self._release_capture()

    def mjpeg_stream(self):
        while True:
            with self.frame_lock:
                frame = self.latest_frame
            if frame is None:
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                line = self.status_line[:52]
                cv2.putText(blank, "Camera chua co hinh.", (70, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(blank, line, (30, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 220, 255), 1, cv2.LINE_AA)
                _, encoded = cv2.imencode(".jpg", blank)
                frame = encoded.tobytes()
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.03)

    def get_state(self) -> dict[str, Any]:
        return {
            "camera_enabled": self.camera_enabled,
            "camera_connected": self.camera_connected,
            "camera_ready": self.camera_ready,
            "camera_source_type": self.camera_source_type,
            "camera_source_value": self.camera_source_value,
            "camera_label": self.camera_label,
            "scan_mode": "continuous",
            "video_feed_url": f"/video_feed?ts={quote(str(time.time()))}",
            "status_line": self.status_line,
            "people_count": len(self.database.get_people()),
            "pending_group_count": self.database.get_pending_group_count(),
        }

    def get_review_state(self) -> dict[str, Any]:
        groups = self.database.get_unknown_groups()
        for group in groups:
            for sample in group["samples"]:
                sample["snapshot_url"] = self.storage.public_url(sample["snapshot_path"])
        return {"people": self.database.get_people(), "groups": groups}

    def import_images(self, files: list[tuple[str, bytes]]) -> dict[str, int]:
        imported_files = 0
        created_groups = 0
        detected_faces = 0
        scanned_frames = 0

        for filename, content in files:
            imported_files += 1
            if self._is_video_file(filename):
                frames, faces = self._import_video_file(filename, content)
                scanned_frames += frames
                detected_faces += faces
                created_groups += faces
                continue

            image = self._decode_uploaded_image(content)
            if image is None:
                continue

            faces = self._process_detected_faces_from_frame(image, label_prefix=f"Imported {filename}")
            detected_faces += faces
            created_groups += faces

        merged_groups = self._merge_similar_pending_groups()
        recheck_result = self.recheck_groups()
        return {
            "imported_files": imported_files,
            "scanned_frames": scanned_frames,
            "detected_faces": detected_faces,
            "created_groups": created_groups,
            "merged_groups": merged_groups,
            "suggested": recheck_result["suggested"],
        }

    def create_person_from_group(self, group_id: str, name: str) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        group = self.database.get_unknown_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        samples = self.database.get_group_sample_payload(group_id)
        try:
            person_id = self.database.create_person_with_samples_returning_id(clean_name, samples, group["cover_snapshot_path"], group["created_at"])
        except Exception as error:
            raise HTTPException(status_code=400, detail="Name already exists") from error

        moved_samples, cover_snapshot_path = self._move_group_samples_to_person_dir(person_id, clean_name, samples)
        self.database.replace_person_samples(person_id, moved_samples, cover_snapshot_path)

        self.database.resolve_group(group_id)
        self.recognizer.refresh()
        self.recheck_groups()

    def attach_group_to_person(self, group_id: str, person_id: str) -> None:
        if not person_id:
            raise HTTPException(status_code=400, detail="Person is required")
        group = self.database.get_unknown_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        person = self.database.get_person(person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        samples = self.database.get_group_sample_payload(group_id)
        moved_samples, cover_snapshot_path = self._move_group_samples_to_person_dir(person_id, person["name"], samples)
        self.database.attach_samples_to_person(person_id, moved_samples)
        if person.get("cover_snapshot_path", "").startswith("snapshots/") and cover_snapshot_path:
            self.database.update_person_cover_snapshot(person_id, cover_snapshot_path)
        self.database.resolve_group(group_id)
        self.recognizer.refresh()
        self.recheck_groups()

    def dismiss_group(self, group_id: str) -> None:
        self.database.dismiss_group(group_id)

    def delete_group_sample(self, group_id: str, sample_id: str) -> None:
        try:
            self.database.delete_group_sample(group_id, sample_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        suggestion = self._best_group_suggestion(group_id)
        self.database.update_group_suggestion(group_id, match_to_dict(suggestion))

    def recheck_groups(self) -> dict[str, int]:
        merged_groups = self._merge_similar_pending_groups()
        scanned = 0
        suggested = 0
        for group in self.database.get_unknown_groups():
            scanned += 1
            suggestion = self._best_group_suggestion(group["id"])
            self.database.update_group_suggestion(group["id"], match_to_dict(suggestion))
            if suggestion:
                suggested += 1
        return {"scanned": scanned, "suggested": suggested, "merged_groups": merged_groups}

    def rebuild_embeddings(self) -> dict[str, int]:
        people = self.database.get_people()
        rebuilt_people = 0
        rebuilt_samples = 0

        for person in people:
            person_id = person["id"]
            person_dir = self._person_dir(person_id, person["name"])
            image_paths = self.storage.list_files(person_dir)
            samples: list[dict[str, Any]] = []
            cover_snapshot_path = ""
            for image_path in image_paths:
                image = self.storage.read_image(image_path)
                if image is None or image.size == 0:
                    continue
                embedding = self.embedder.compute(image)
                samples.append(
                    {
                        "embedding": json.dumps(embedding.tolist()),
                        "snapshot_path": image_path,
                        "created_at": self._timestamp(),
                    }
                )
                rebuilt_samples += 1
                if not cover_snapshot_path:
                    cover_snapshot_path = image_path

            if samples:
                self.database.replace_person_samples(person_id, samples, cover_snapshot_path)
                rebuilt_people += 1

        self.recognizer.refresh()
        return {"rebuilt_people": rebuilt_people, "rebuilt_samples": rebuilt_samples}


def match_to_dict(match: MatchResult | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {"person_id": match.person_id, "person_name": match.person_name, "score": match.score}
