"""
Face detection with YuNet (cv2.FaceDetectorYN).

Replaces the frontal-only Haar cascade. YuNet detects small and off-axis faces
far more reliably, which matters because an undetected student was previously
dropped from the denominator rather than lowering the class score — i.e.
looking away used to *raise* the reported engagement.

Ships inside OpenCV >= 4.5.4, so this adds no Python dependency; only the
~230 KB ONNX file is fetched (see `scripts/fetch_models.py`).
"""
import os
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MODEL_SEARCH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@dataclass
class FaceDetection:
    """One detected face in absolute pixel coordinates."""
    x: int
    y: int
    w: int
    h: int
    score: float
    landmarks: np.ndarray = field(default_factory=lambda: np.zeros((5, 2), np.float32))

    @property
    def size_px(self) -> int:
        """Smaller bbox edge — the resolution budget available to downstream models."""
        return int(min(self.w, self.h))

    def bbox_norm(self, frame_w: int, frame_h: int) -> list[float]:
        return [self.x / frame_w, self.y / frame_h, self.w / frame_w, self.h / frame_h]


class YuNetDetector:
    def __init__(
        self,
        model_path: str,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
        tiling: bool = False,
        tile_overlap: float = 0.2,
    ):
        path = model_path if os.path.isabs(model_path) else os.path.join(_MODEL_SEARCH_ROOT, model_path)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"YuNet model not found at {path}. Run: python scripts/fetch_models.py"
            )

        self._score_threshold = score_threshold
        self._nms_threshold = nms_threshold
        self._tiling = tiling
        self._tile_overlap = tile_overlap
        self._input_size: Optional[tuple[int, int]] = None
        self._detector = cv2.FaceDetectorYN.create(
            path, "", (320, 320), score_threshold, nms_threshold, top_k
        )
        # One YuNet instance is a process-wide singleton shared by every
        # session (frame_distributor._get_detector). setInputSize() mutates
        # it, and detect() calls land on the executor's worker threads, so
        # two sessions streaming at different resolutions concurrently could
        # race: session A sets 1920x1080, session B sets 640x480 before A's
        # detect() runs, and A gets B's frame geometry back. detect() itself
        # is ~1-2ms (YuNet's own benchmark), so serializing it costs far less
        # than one extra pose/gaze pass would.
        self._lock = threading.Lock()
        logger.info("[yunet] loaded %s (tiling=%s)", os.path.basename(path), tiling)

    def detect(self, frame_bgr: np.ndarray) -> list[FaceDetection]:
        h, w = frame_bgr.shape[:2]
        with self._lock:
            if self._tiling:
                return self._detect_tiled(frame_bgr, w, h)
            return self._detect_whole(frame_bgr, w, h)

    def _detect_whole(self, image: np.ndarray, w: int, h: int) -> list[FaceDetection]:
        if self._input_size != (w, h):
            self._detector.setInputSize((w, h))
            self._input_size = (w, h)
        _, raw = self._detector.detect(image)
        return _rows_to_detections(raw, w, h)

    def _detect_tiled(self, frame_bgr: np.ndarray, w: int, h: int) -> list[FaceDetection]:
        """
        Run detection on overlapping half-frame tiles and merge with NMS.

        A distant face occupies more of a tile than of the full frame, so the
        detector sees it at a scale closer to its training distribution. Costs
        one extra forward pass per tile; only worth enabling when back-row
        recall measures poorly on the annotated set.
        """
        tw, th = w // 2, h // 2
        ox, oy = int(tw * self._tile_overlap), int(th * self._tile_overlap)

        merged: list[FaceDetection] = []
        for ty in range(0, h - oy, th - oy):
            for tx in range(0, w - ox, tw - ox):
                x2, y2 = min(w, tx + tw), min(h, ty + th)
                tile = frame_bgr[ty:y2, tx:x2]
                if tile.size == 0:
                    continue
                # setInputSize per tile; the edge tiles are smaller than the rest
                self._detector.setInputSize((tile.shape[1], tile.shape[0]))
                self._input_size = (tile.shape[1], tile.shape[0])
                _, raw = self._detector.detect(tile)
                for det in _rows_to_detections(raw, tile.shape[1], tile.shape[0]):
                    det.x += tx
                    det.y += ty
                    det.landmarks[:, 0] += tx
                    det.landmarks[:, 1] += ty
                    merged.append(det)

        return _nms(merged, self._score_threshold, self._nms_threshold)


def _rows_to_detections(raw, w: int, h: int) -> list[FaceDetection]:
    if raw is None or len(raw) == 0:
        return []
    out: list[FaceDetection] = []
    for row in raw:
        x, y, bw, bh = (int(round(v)) for v in row[:4])
        # YuNet can return boxes that run past the frame edge
        x, y = max(0, x), max(0, y)
        bw, bh = min(bw, w - x), min(bh, h - y)
        if bw <= 0 or bh <= 0:
            continue
        out.append(FaceDetection(
            x=x, y=y, w=bw, h=bh,
            score=float(row[14]),
            landmarks=np.array(row[4:14], np.float32).reshape(5, 2),
        ))
    return out


def _nms(dets: list[FaceDetection], score_threshold: float, nms_threshold: float) -> list[FaceDetection]:
    if len(dets) <= 1:
        return dets
    boxes = [[d.x, d.y, d.w, d.h] for d in dets]
    scores = [d.score for d in dets]
    keep = cv2.dnn.NMSBoxes(boxes, scores, score_threshold, nms_threshold)
    if keep is None or len(keep) == 0:
        return []
    return [dets[int(i)] for i in np.array(keep).flatten()]
