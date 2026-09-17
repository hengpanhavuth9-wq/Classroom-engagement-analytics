"""
Head pose via 6DRepNet360 (thohemp, IEEE TIP 2024), ONNX export from
PINTO0309/PINTO_model_zoo (423_6DRepNet360, sixdrepnet360_Nx3x224x224.onnx).

OPT-IN, NOT THE DEFAULT (settings.HEAD_POSE_BACKEND, default "mediapipe").
This is a straight drop-in swap for the yaw/pitch source that currently comes
from repurposing MediaPipe FaceLandmarker's transformation matrix
(head_pose.pose_from_matrix) — a model trained for landmarks, not pose,
pressed into service because the pipeline already runs it. 6DRepNet360 is a
model trained specifically for full-range head pose, so it should be more
robust at the small, off-axis crops a classroom back row produces — but that
is a claim to verify with eval/run_eval.py against real footage before
trusting it over the current default, not something to assume from a
benchmark paper's numbers on AFLW2000/BIWI. See ENGAGEMENT-MODEL-DECISIONS.md
§4 and the gaze/head-pose sign-convention TODOs this module adds alongside
the existing ones — none of these signs have been checked against ground
truth, and getting one wrong silently inverts desk_work/off_task the same
way a wrong MediaPipe pitch sign would.

Preprocessing (fixed by the exported graph, not a free parameter):
  crop with ~1.2x margin -> resize 256x256 -> center-crop to 224x224
  -> BGR->RGB -> /255 -> ImageNet normalize -> CHW -> batch
Output: a single [1, 3] tensor of (yaw, pitch, roll) in degrees directly —
no bin decoding needed, unlike gaze_onnx.py's classification head.

Reference: https://github.com/thohemp/6DRepNet360
           https://github.com/PINTO0309/PINTO_model_zoo/tree/main/423_6DRepNet360
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from .yunet_detector import FaceDetection

logger = logging.getLogger(__name__)

_MODEL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "weights", "sixdrepnet360_Nx3x224x224.onnx"
))

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class SixDRepNetPose:
    """Camera-relative head pose, in degrees — same shape as head_pose.HeadPose."""
    yaw: float
    pitch: float
    roll: float


class SixDRepNetONNX:
    def __init__(self, margin: float = 0.1, intra_op_threads: int = 4):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(
                f"6DRepNet360 ONNX model not found at {_MODEL_PATH}. "
                "Run: python scripts/fetch_models.py"
            )
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, intra_op_threads)
        self._session = ort.InferenceSession(_MODEL_PATH, opts, providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]
        self._margin = margin
        logger.info("[head_pose_sixdrepnet] loaded sixdrepnet360_Nx3x224x224.onnx")

    def estimate(self, frame_bgr: np.ndarray, det: FaceDetection) -> Optional[SixDRepNetPose]:
        crop = self._crop(frame_bgr, det)
        if crop is None:
            return None
        yaw, pitch, roll = self._session.run(
            self._output_names, {self._input_name: self._preprocess(crop)}
        )[0][0]
        return SixDRepNetPose(yaw=round(float(yaw), 2), pitch=round(float(pitch), 2), roll=round(float(roll), 2))

    def _crop(self, frame_bgr: np.ndarray, det: FaceDetection) -> Optional[np.ndarray]:
        """Expand the detection box by `margin` on each side. Default 0.1
        matches the PINTO reference demo's `ew = w * 1.2` (total width
        1.2x = original + 0.1x margin on each side), then the fixed
        256->224 center-crop in `_preprocess` does the rest."""
        h, w = frame_bgr.shape[:2]
        mx, my = int(det.w * self._margin), int(det.h * self._margin)
        x1, y1 = max(0, det.x - mx), max(0, det.y - my)
        x2, y2 = min(w, det.x + det.w + mx), min(h, det.y + det.h + my)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        crop = frame_bgr[y1:y2, x1:x2]
        return crop if crop.size else None

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_bgr, (256, 256))
        cropped = resized[16:240, 16:240]  # -> 224x224, per the reference demo
        rgb = cropped[..., ::-1].astype(np.float32) / 255.0
        normalized = (rgb - _MEAN) / _STD
        return np.expand_dims(normalized.transpose(2, 0, 1), 0).astype(np.float32)
