from __future__ import annotations

import threading

import cv2
import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1


class FaceEmbedder:
    def __init__(self) -> None:
        self.model = InceptionResnetV1(pretrained="vggface2").eval()
        self.lock = threading.Lock()

    def compute(self, face_image: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (160, 160))
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0
        tensor = ((tensor - 0.5) / 0.5).unsqueeze(0)
        with self.lock:
            with torch.no_grad():
                embedding = self.model(tensor).squeeze(0).cpu().numpy().astype(np.float32)
        norm = np.linalg.norm(embedding)
        return embedding if norm == 0 else embedding / norm
