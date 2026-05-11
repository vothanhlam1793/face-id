from __future__ import annotations

from typing import Any

import numpy as np

from app.config import MATCH_THRESHOLD_SUGGEST
from app.core.database import FaceDatabase
from app.core.models import MatchResult


class FaceRecognizer:
    def __init__(self, database: FaceDatabase) -> None:
        self.database = database
        self.known_samples = self.database.get_samples()

    def refresh(self) -> None:
        self.known_samples = self.database.get_samples()

    def best_match(self, embedding: np.ndarray) -> MatchResult | None:
        best: dict[str, Any] | None = None
        best_score = -1.0
        for sample in self.known_samples:
            score = float(np.dot(embedding, sample["embedding"]))
            if score > best_score:
                best_score = score
                best = sample
        if best is None:
            return None
        return MatchResult(
            person_id=best["person_id"],
            person_name=best["person_name"],
            score=round(best_score, 4),
        )

    def best_group_suggestion(self, samples: list[dict[str, Any]]) -> MatchResult | None:
        best: MatchResult | None = None
        best_score = -1.0
        for sample in samples:
            embedding = np.array(json_loads(sample["embedding"]), dtype=np.float32)
            match = self.best_match(embedding)
            if match and match.score > best_score:
                best = match
                best_score = match.score
        if best and best.score >= MATCH_THRESHOLD_SUGGEST:
            return best
        return None


def json_loads(value: Any) -> Any:
    if isinstance(value, str):
        import json

        return json.loads(value)
    return value
