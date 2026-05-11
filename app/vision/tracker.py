from __future__ import annotations

import time
import uuid

from app.config import MAX_ACTIVE_TRACKS, TRACK_IOU_THRESHOLD, TRACK_TTL_SECONDS
from app.core.models import BoundingBox, TrackState


def compute_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    denom = area1 + area2 - inter
    return inter / denom if denom > 0 else 0.0


class SimpleFaceTracker:
    def __init__(self) -> None:
        self.active_tracks: dict[str, TrackState] = {}

    def match_or_create(self, box: BoundingBox, now: float | None = None) -> TrackState:
        now = time.time() if now is None else now
        stale_ids = [track_id for track_id, track in self.active_tracks.items() if now - track.last_seen_at > TRACK_TTL_SECONDS]
        for track_id in stale_ids:
            self.active_tracks.pop(track_id, None)

        best_track_id = None
        best_iou = 0.0
        for track_id, track in self.active_tracks.items():
            iou = compute_iou(box, track.box)
            if iou > best_iou:
                best_iou = iou
                best_track_id = track_id

        if best_track_id and best_iou >= TRACK_IOU_THRESHOLD:
            track = self.active_tracks[best_track_id]
            track.box = box
            track.last_seen_at = now
            return track

        if len(self.active_tracks) >= MAX_ACTIVE_TRACKS and self.active_tracks:
            oldest_track_id = min(self.active_tracks, key=lambda key: self.active_tracks[key].last_seen_at)
            self.active_tracks.pop(oldest_track_id, None)

        track = TrackState(track_id=str(uuid.uuid4()), box=box, last_seen_at=now)
        self.active_tracks[track.track_id] = track
        return track
