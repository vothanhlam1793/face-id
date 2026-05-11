from __future__ import annotations

import numpy as np
from ultralytics import YOLO


class FaceDetector:
    def __init__(self, model_path: str) -> None:
        self.model = YOLO(model_path)

    def detect(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        results = self.model.predict(frame, conf=0.35, imgsz=640, verbose=False)
        if not results or results[0].boxes is None:
            return []
        return [tuple(box.tolist()) for box in results[0].boxes.xyxy.cpu().numpy().astype(int)]
