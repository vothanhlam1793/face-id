from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


BoundingBox = tuple[int, int, int, int]


@dataclass
class MatchResult:
    person_id: str
    person_name: str
    score: float


@dataclass
class TrackState:
    track_id: str
    box: BoundingBox
    last_seen_at: float
    group_id: str | None = None
    label: str = "Unknown"
    sample_count: int = 0
    best_quality: float = 0.0
    last_sample_at: float = 0.0
    recognized_person_id: str | None = None


@dataclass
class GroupSample:
    embedding: np.ndarray
    snapshot_path: str
    created_at: str
    quality_score: float | None = None


@dataclass
class UnknownGroup:
    id: str
    label: str
    created_at: str
    updated_at: str
    status: str
    cover_snapshot_path: str
    suggested_person_id: str | None = None
    suggested_person_name: str | None = None
    suggested_score: float | None = None
    samples: list[dict[str, Any]] = field(default_factory=list)
    sample_count: int = 0
