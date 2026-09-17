"""
Gaze-only pipeline orchestrator.

    YuNet (full frame)  →  per-face crop  →  MediaPipe FaceLandmarker
                                          →  head pose (transformation matrix)
                                          →  eye gaze ONNX  [above pixel gate,
                                                             round-robin budget]
                                          →  tracker  →  AttentionEngine

One detector, one face list. The previous version ran Haar and MediaPipe
independently and then indexed one list with the other's index, which
attributed measurements to the wrong students whenever the two disagreed.

Heavy models are process-wide singletons; per-session state (tracker,
attention engine, gaze scheduling) lives on the instance, so one
FrameDistributor is created per session rather than shared across them.

PRIVACY: frames exist only as numpy arrays in RAM and are released when this
returns. Nothing per-student that could follow a person across the session —
no track ids — crosses into the payload; the overlay carries this frame's
geometry and nothing else.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..config import settings
from .engagement_engine import AttentionConfig, AttentionEngine, AttentionState
from .head_pose import HeadPose, angular_deviation, pose_from_matrix
from .mediapipe_init import FacePipelineConfig
from .tracker import FaceTracker
from .yunet_detector import FaceDetection, YuNetDetector

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=settings.PIPELINE_WORKERS)

_detector: Optional[YuNetDetector] = None
_gaze_model = None
_gaze_load_failed = False
_mp_pipeline: Optional[FacePipelineConfig] = None
_sixdrepnet_model = None
_sixdrepnet_load_failed = False

# The worker pool hits these loaders concurrently on the first frame. Without
# the lock every worker sees `None` and builds its own copy — four MediaPipe
# pipelines, each with its own GL context, three of them then discarded.
_model_lock = threading.Lock()


def _get_detector() -> YuNetDetector:
    global _detector
    if _detector is not None:
        return _detector
    with _model_lock:
        if _detector is not None:
            return _detector
        _detector = YuNetDetector(
            settings.YUNET_MODEL_PATH,
            score_threshold=settings.YUNET_SCORE_THRESHOLD,
            nms_threshold=settings.YUNET_NMS_THRESHOLD,
            tiling=settings.DETECT_TILING,
            tile_overlap=settings.DETECT_TILE_OVERLAP,
        )
        return _detector


def _get_mp_pipeline() -> FacePipelineConfig:
    global _mp_pipeline
    if _mp_pipeline is not None:
        return _mp_pipeline
    with _model_lock:
        if _mp_pipeline is None:
            _mp_pipeline = FacePipelineConfig(
                max_faces=settings.MAX_FACES_PER_CAMERA,
                crop_pool_size=settings.PIPELINE_WORKERS,
            )
        return _mp_pipeline


def _get_gaze_model():
    """
    Load the eye-gaze model once. A failure is cached rather than retried:
    the previous version re-attempted the load for every face of every frame.
    """
    global _gaze_model, _gaze_load_failed
    if _gaze_model is not None or _gaze_load_failed:
        return _gaze_model
    with _model_lock:
        if _gaze_model is not None or _gaze_load_failed:
            return _gaze_model
        try:
            from .gaze_onnx import GazeEstimatorONNX
            _gaze_model = GazeEstimatorONNX(
                backbone=settings.GAZE_BACKBONE,
                margin=settings.GAZE_CROP_MARGIN,
                intra_op_threads=settings.ONNX_INTRA_OP_THREADS,
            )
        except Exception as exc:
            _gaze_load_failed = True
            logger.warning(
                "[pipeline] eye-gaze model unavailable (%s). Running on head pose only — "
                "students are NOT silently scored as engaged.", exc
            )
        return _gaze_model


def _get_sixdrepnet_model():
    """Only loaded when settings.HEAD_POSE_BACKEND == "sixdrepnet" — see config.py."""
    global _sixdrepnet_model, _sixdrepnet_load_failed
    if _sixdrepnet_model is not None or _sixdrepnet_load_failed:
        return _sixdrepnet_model
    with _model_lock:
        if _sixdrepnet_model is not None or _sixdrepnet_load_failed:
            return _sixdrepnet_model
        try:
            from .head_pose_sixdrepnet import SixDRepNetONNX
            _sixdrepnet_model = SixDRepNetONNX(
                margin=settings.SIXDREPNET_CROP_MARGIN,
                intra_op_threads=settings.ONNX_INTRA_OP_THREADS,
            )
        except Exception as exc:
            _sixdrepnet_load_failed = True
            logger.warning(
                "[pipeline] 6DRepNet360 unavailable (%s). "
                "Set HEAD_POSE_BACKEND=mediapipe or run scripts/fetch_models.py.", exc
            )
        return _sixdrepnet_model


@dataclass
class FaceObservation:
    """One student's measurement for one frame, in normalised overlay terms."""
    bbox_norm: list[float]
    face_px: int
    state: AttentionState
    yaw_dev: float = 0.0
    pitch_dev: float = 0.0
    on_task_ratio: Optional[float] = None
    has_gaze: bool = False


class FrameDistributor:
    """Runs the pipeline for one session. Not shared between sessions."""

    def __init__(self, max_faces: int = 40, config: Optional[AttentionConfig] = None):
        self.max_faces = max_faces
        self.config = config or AttentionConfig.from_settings(settings)
        self.engine = AttentionEngine(self.config)
        self.tracker = FaceTracker(
            iou_threshold=settings.TRACK_IOU_THRESHOLD,
            max_lost_frames=settings.TRACK_MAX_LOST_FRAMES,
        )
        self._gaze_cache: dict[int, tuple[float, float]] = {}
        self._gaze_seen_at: dict[int, int] = {}
        self._frame_index = 0

    def start_calibration(self, now: float) -> None:
        self.engine.start_calibration(now)

    def finish_calibration(self) -> int:
        return self.engine.finish_calibration()

    async def process_frame(self, frame_bgr: np.ndarray, now: float) -> list[FaceObservation]:
        loop = asyncio.get_running_loop()
        h, w = frame_bgr.shape[:2]
        self._frame_index += 1

        detections = await loop.run_in_executor(executor, _get_detector().detect, frame_bgr)
        if not detections:
            # Still age lost tracks on a blank frame — otherwise a student who
            # steps out of view (or a camera drop) never ages out of the
            # tracker or the attention engine, and state_counts keeps
            # reporting their last-seen state as if it were still current.
            self.tracker.update([])
            self._forget_dropped_tracks()
            return []
        detections = sorted(detections, key=lambda d: d.score, reverse=True)[: self.max_faces]

        tracked = self.tracker.update(detections)
        gaze_targets = self._select_gaze_targets(tracked)

        results = await asyncio.gather(*[
            loop.run_in_executor(
                executor, self._analyse_face, frame_bgr, det, track_id in gaze_targets
            )
            for track_id, det in tracked
        ])

        observations: list[FaceObservation] = []
        for (track_id, det), (pose, gaze) in zip(tracked, results):
            if gaze is not None:
                self._gaze_cache[track_id] = gaze
                self._gaze_seen_at[track_id] = self._frame_index
            blended_gaze = self._gaze_cache.get(track_id)

            student = self.engine.observe(
                track_id=track_id,
                now=now,
                head_pose=pose,
                gaze=blended_gaze,
                face_px=det.size_px,
            )

            yaw_dev, pitch_dev = self._deviation(student, pose)
            observations.append(FaceObservation(
                bbox_norm=det.bbox_norm(w, h),
                face_px=det.size_px,
                state=student.state,
                yaw_dev=round(yaw_dev, 1),
                pitch_dev=round(pitch_dev, 1),
                on_task_ratio=student.on_task_ratio(
                    now, self.config.window_seconds, self.config.desk_work_weight
                ),
                has_gaze=blended_gaze is not None,
            ))

        self._forget_dropped_tracks()
        return observations

    def _deviation(self, student, pose: Optional[HeadPose]) -> tuple[float, float]:
        """Angles shown on the overlay are relative to the student's reference."""
        if pose is None:
            return 0.0, 0.0
        reference = student.reference
        if reference is None:
            return pose.yaw, pose.pitch
        smoothed = HeadPose(
            yaw=student.ema_yaw if student.ema_yaw is not None else pose.yaw,
            pitch=student.ema_pitch if student.ema_pitch is not None else pose.pitch,
            roll=0.0,
        )
        return angular_deviation(smoothed, reference)

    def _select_gaze_targets(self, tracked: list[tuple[int, FaceDetection]]) -> set[int]:
        """
        Choose which faces get an eye-gaze pass this frame.

        Eye gaze refines an EMA-smoothed signal read over a multi-second
        window, so every student does not need it every frame. Refreshing the
        stalest few keeps per-frame cost flat as the class grows — a 40-student
        room costs the same as a 10-student one — instead of making throughput
        a function of attendance.
        """
        if _get_gaze_model() is None:
            return set()
        eligible = [
            track_id for track_id, det in tracked
            if det.size_px >= self.config.min_face_px_for_gaze
        ]
        eligible.sort(key=lambda t: self._gaze_seen_at.get(t, -1))
        return set(eligible[: settings.GAZE_REFRESH_BUDGET])

    def _analyse_face(
        self, frame_bgr: np.ndarray, det: FaceDetection, want_gaze: bool
    ) -> tuple[Optional[HeadPose], Optional[tuple[float, float]]]:
        """Runs on a worker thread: head pose always, eye gaze only when budgeted."""
        pose = (
            self._pose_sixdrepnet(frame_bgr, det)
            if settings.HEAD_POSE_BACKEND == "sixdrepnet"
            else self._pose_mediapipe(frame_bgr, det)
        )

        gaze = None
        if want_gaze:
            try:
                model = _get_gaze_model()
                if model is not None:
                    result = model.estimate(frame_bgr, det)
                    if result is not None:
                        gaze = (result.yaw, result.pitch)
            except Exception as exc:
                logger.debug("[pipeline] eye gaze failed: %s", exc)

        return pose, gaze

    def _pose_mediapipe(self, frame_bgr: np.ndarray, det: FaceDetection) -> Optional[HeadPose]:
        try:
            crop = _crop_with_margin(frame_bgr, det, margin=0.15)
            if crop is None:
                return None
            result = _get_mp_pipeline().process_crop(crop)
            if not result.facial_transformation_matrixes:
                return None
            return pose_from_matrix(result.facial_transformation_matrixes[0])
        except Exception as exc:
            logger.debug("[pipeline] head pose (mediapipe) failed: %s", exc)
            return None

    def _pose_sixdrepnet(self, frame_bgr: np.ndarray, det: FaceDetection) -> Optional[HeadPose]:
        try:
            model = _get_sixdrepnet_model()
            if model is None:
                return None
            result = model.estimate(frame_bgr, det)
            if result is None:
                return None
            return HeadPose(
                yaw=result.yaw * settings.SIXDREPNET_YAW_SIGN,
                pitch=result.pitch * settings.SIXDREPNET_PITCH_SIGN,
                roll=result.roll,
            )
        except Exception as exc:
            logger.debug("[pipeline] head pose (sixdrepnet) failed: %s", exc)
            return None

    def _forget_dropped_tracks(self) -> None:
        live = set(self.engine.students) & set(self.tracker._tracks)
        for track_id in list(self._gaze_cache):
            if track_id not in live:
                self._gaze_cache.pop(track_id, None)
                self._gaze_seen_at.pop(track_id, None)
        for track_id in list(self.engine.students):
            if track_id not in self.tracker._tracks:
                self.engine.drop(track_id)

    def aggregate_class_metrics(
        self, observations: list[FaceObservation], now: float, expected_count: Optional[int] = None
    ) -> dict:
        """
        Build the payload that crosses the privacy boundary.

        Everything here is either a class-level aggregate or this frame's
        geometry. No identifier, and nothing that links a box in one frame to a
        box in the next.
        """
        metrics = self.engine.class_metrics(now, expected_count=expected_count)
        metrics["faces"] = [
            {
                "bbox":          o.bbox_norm,
                "yaw":           o.yaw_dev,
                "pitch":         o.pitch_dev,
                "state":         o.state.value,
                "on_task_ratio": None if o.on_task_ratio is None else round(o.on_task_ratio, 3),
                "measured":      o.state.is_measured,
                "has_gaze":      o.has_gaze,
            }
            for o in observations
        ]
        metrics["detected_count"] = len(observations)
        metrics["gaze_model_loaded"] = _gaze_model is not None
        return metrics


def _crop_with_margin(frame_bgr: np.ndarray, det: FaceDetection, margin: float) -> Optional[np.ndarray]:
    h, w = frame_bgr.shape[:2]
    mx, my = int(det.w * margin), int(det.h * margin)
    x1, y1 = max(0, det.x - mx), max(0, det.y - my)
    x2, y2 = min(w, det.x + det.w + mx), min(h, det.y + det.h + my)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    crop = frame_bgr[y1:y2, x1:x2]
    return crop if crop.size else None
