"""
Gaze-only attention model.

This module is the single definition of what "engaged" means. The previous
version was dead code — `frame_distributor` re-inlined its own copy of the
formula — so tuning constants here changed nothing at runtime. Everything now
routes through `AttentionEngine`.

Three decisions shape it:

1. Attention is measured RELATIVE to each student's own calibrated reference,
   not as an absolute cone around the camera axis. A camera-relative test
   confounds seat position with attention: a front-left student looking at the
   board has a large camera-relative yaw and would score as distracted, while
   a back-row student staring at the lens would score as attentive. Working in
   relative terms also cancels the camera-vs-board offset and the pose
   estimator's per-subject bias, which no absolute threshold can reach.

2. Looking DOWN is not the same as looking AWAY. A student reading notes is on
   task; scoring them off-task produces exactly the false negatives a teacher
   will reject. `desk_work` is therefore its own state, and how much it counts
   toward engagement is a weight the teacher-feedback loop fits rather than a
   number we guess.

3. The reported metric is an on-task RATIO over a rolling window, not a
   per-frame binary. Per-student instantaneous gaze at classroom distance is
   not reliable enough to act on frame by frame, and momentary time sampling
   over a window is what classroom-observation practice actually uses.
"""
import os
import statistics
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

from .head_pose import HeadPose, angular_deviation


class AttentionState(str, Enum):
    ON_TASK   = "on_task"
    DESK_WORK = "desk_work"
    OFF_TASK  = "off_task"
    UNKNOWN   = "unknown"

    @property
    def is_measured(self) -> bool:
        """UNKNOWN is excluded from both numerator and denominator."""
        return self is not AttentionState.UNKNOWN


@dataclass(frozen=True)
class AttentionConfig:
    yaw_enter_deg: float = 25.0
    yaw_exit_deg: float = 32.0
    desk_work_pitch_deg: float = 18.0
    desk_work_weight: float = 1.0
    ema_alpha: float = 0.4
    window_seconds: float = 20.0
    on_task_floor: float = 0.5
    gaze_blend_weight: float = 0.3
    # gaze_onnx.py documents no sign convention of its own (unlike head_pose.py,
    # which fixes one and flags it TODO-unverified). If eval/verify_pose_signs.py
    # — extended to also compare gaze against head pose on the same detections
    # — shows they disagree, flip the matching value to -1.0 here rather than
    # guessing; a wrong sign makes gaze fight head pose instead of refining it.
    gaze_yaw_sign: float = 1.0
    gaze_pitch_sign: float = 1.0
    min_face_px: int = 24
    min_face_px_for_gaze: int = 80
    calibration_seconds: float = 5.0

    @classmethod
    def from_settings(cls, settings) -> "AttentionConfig":
        config = cls(
            yaw_enter_deg=settings.ATTENTION_YAW_ENTER_DEG,
            yaw_exit_deg=settings.ATTENTION_YAW_EXIT_DEG,
            desk_work_pitch_deg=settings.DESK_WORK_PITCH_DEG,
            desk_work_weight=settings.DESK_WORK_WEIGHT,
            ema_alpha=settings.EMA_ALPHA,
            window_seconds=settings.ONTASK_WINDOW_SECONDS,
            on_task_floor=settings.ONTASK_FLOOR,
            gaze_blend_weight=settings.GAZE_BLEND_WEIGHT,
            gaze_yaw_sign=settings.GAZE_YAW_SIGN,
            gaze_pitch_sign=settings.GAZE_PITCH_SIGN,
            min_face_px=settings.MIN_FACE_PX,
            min_face_px_for_gaze=settings.MIN_FACE_PX_FOR_GAZE,
            calibration_seconds=settings.CALIBRATION_SECONDS,
        )
        path = getattr(settings, "ATTENTION_CONFIG_PATH", "") or ""
        if path and os.path.exists(path):
            config = cls.from_yaml(path, base=config)
        return config

    @classmethod
    def from_yaml(cls, path: str, base: Optional["AttentionConfig"] = None) -> "AttentionConfig":
        """Overlay a YAML of tuned fields (from eval/sweep.py or tune_from_feedback.py)."""
        import yaml
        current = base or cls()
        with open(path, encoding="utf-8") as fh:
            overrides = yaml.safe_load(fh) or {}
        unknown = set(overrides) - set(current.__dict__)
        if unknown:
            raise ValueError(f"Unknown AttentionConfig keys in {path}: {sorted(unknown)}")
        return replace(current, **overrides)


@dataclass
class StudentAttention:
    """Per-track attention state. One instance per tracked student per session."""
    track_id: int
    reference: Optional[HeadPose] = None
    ema_yaw: Optional[float] = None
    ema_pitch: Optional[float] = None
    state: AttentionState = AttentionState.UNKNOWN
    _calibration: list[tuple[float, float]] = field(default_factory=list)
    _history: deque = field(default_factory=deque)   # (timestamp, AttentionState)

    @property
    def is_calibrated(self) -> bool:
        return self.reference is not None

    def on_task_ratio(self, now: float, window_seconds: float, desk_work_weight: float) -> Optional[float]:
        """
        Fraction of measured samples in the window that were on task.

        None when the window holds no measured sample at all — that student is
        uncovered, which is reported separately rather than being averaged in
        as if it were disengagement.
        """
        self._evict(now, window_seconds)
        measured = [s for _, s in self._history if s.is_measured]
        if not measured:
            return None
        credit = sum(
            1.0 if s is AttentionState.ON_TASK else desk_work_weight if s is AttentionState.DESK_WORK else 0.0
            for s in measured
        )
        return credit / len(measured)

    def _evict(self, now: float, window_seconds: float) -> None:
        cutoff = now - window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()


class AttentionEngine:
    """
    Holds per-student attention state for one session.

    Timestamps are passed in rather than read from the clock so the offline
    eval harness can replay a recording at any speed and get identical results.
    """

    def __init__(self, config: AttentionConfig):
        self.config = config
        self.students: dict[int, StudentAttention] = {}
        self._calibrating_until: Optional[float] = None

    # ── Calibration ───────────────────────────────────────────────────────────

    def start_calibration(self, now: float) -> None:
        """Begin the "everyone look at the board" window."""
        self._calibrating_until = now + self.config.calibration_seconds
        for student in self.students.values():
            student._calibration.clear()

    @property
    def is_calibrating(self) -> bool:
        return self._calibrating_until is not None

    def finish_calibration(self) -> int:
        """
        Freeze each student's reference pose as the median of their samples.

        Median rather than mean because a student who glanced away mid-window
        should not drag their own reference off the board.
        """
        self._calibrating_until = None
        calibrated = 0
        for student in self.students.values():
            if len(student._calibration) < 3:
                continue
            yaws = [y for y, _ in student._calibration]
            pitches = [p for _, p in student._calibration]
            student.reference = HeadPose(
                yaw=statistics.median(yaws), pitch=statistics.median(pitches), roll=0.0
            )
            student._calibration.clear()
            calibrated += 1
        return calibrated

    def _fallback_reference(self) -> Optional[HeadPose]:
        """
        Class-median reference, used for students who arrived after calibration.

        Weaker than a personal reference — it carries that student's seat
        offset — but far better than an absolute camera-relative threshold.
        """
        refs = [s.reference for s in self.students.values() if s.reference is not None]
        if not refs:
            return None
        return HeadPose(
            yaw=statistics.median([r.yaw for r in refs]),
            pitch=statistics.median([r.pitch for r in refs]),
            roll=0.0,
        )

    # ── Per-frame observation ────────────────────────────────────────────

    def observe(
        self,
        track_id: int,
        now: float,
        head_pose: Optional[HeadPose],
        gaze: Optional[tuple[float, float]] = None,
        face_px: int = 0,
    ) -> StudentAttention:
        """Fold one frame's measurement for one student into their state."""
        student = self.students.setdefault(track_id, StudentAttention(track_id=track_id))

        if head_pose is None or face_px < self.config.min_face_px:
            student.state = AttentionState.UNKNOWN
            student._history.append((now, AttentionState.UNKNOWN))
            return student

        yaw, pitch = self._blend(head_pose, gaze, face_px)
        student.ema_yaw = _ema(student.ema_yaw, yaw, self.config.ema_alpha)
        student.ema_pitch = _ema(student.ema_pitch, pitch, self.config.ema_alpha)

        if self.is_calibrating:
            student._calibration.append((student.ema_yaw, student.ema_pitch))
            student.state = AttentionState.UNKNOWN
            student._history.append((now, AttentionState.UNKNOWN))
            return student

        reference = student.reference or self._fallback_reference()
        if reference is None:
            student.state = AttentionState.UNKNOWN
            student._history.append((now, AttentionState.UNKNOWN))
            return student

        smoothed = HeadPose(yaw=student.ema_yaw, pitch=student.ema_pitch, roll=0.0)
        student.state = self._classify(smoothed, reference, student.state)
        student._history.append((now, student.state))
        return student

    def _blend(
        self, head_pose: HeadPose, gaze: Optional[tuple[float, float]], face_px: int
    ) -> tuple[float, float]:
        """
        Combine head pose with eye gaze where the face is big enough to trust it.

        Both estimate the same quantity — where the student is looking, in
        camera-relative degrees — so this is a weighted average, not a sum.
        Below the pixel gate the gaze model is reading upsampling artifacts and
        is ignored entirely.
        """
        if gaze is None or face_px < self.config.min_face_px_for_gaze:
            return head_pose.yaw, head_pose.pitch
        w = self.config.gaze_blend_weight
        gaze_yaw, gaze_pitch = gaze
        gaze_yaw *= self.config.gaze_yaw_sign
        gaze_pitch *= self.config.gaze_pitch_sign
        return (
            (1.0 - w) * head_pose.yaw + w * gaze_yaw,
            (1.0 - w) * head_pose.pitch + w * gaze_pitch,
        )

    def _classify(
        self, pose: HeadPose, reference: HeadPose, previous: AttentionState
    ) -> AttentionState:
        dev_yaw, dev_pitch = angular_deviation(pose, reference)

        # Hysteresis: a student already counted as attentive has to swing
        # further to lose it, so borderline poses do not flap frame to frame.
        was_attentive = previous in (AttentionState.ON_TASK, AttentionState.DESK_WORK)
        threshold = self.config.yaw_exit_deg if was_attentive else self.config.yaw_enter_deg

        if abs(dev_yaw) > threshold:
            return AttentionState.OFF_TASK
        if dev_pitch > self.config.desk_work_pitch_deg:
            return AttentionState.DESK_WORK
        return AttentionState.ON_TASK

    def drop(self, track_id: int) -> None:
        self.students.pop(track_id, None)

    # ── Class-level aggregation ──────────────────────────────────────────

    def class_metrics(self, now: float, expected_count: Optional[int] = None) -> dict:
        """
        Aggregate to the class level.

        Reports the mean on-task ratio AND the number of students below the
        floor: a plain mean hides a disengaged minority, which is precisely the
        situation a teacher needs surfaced. Coverage is reported explicitly so
        the dashboard can say "18 of 22 tracked" rather than quietly shrinking
        its own denominator.
        """
        cfg = self.config
        ratios: list[float] = []
        state_counts = {s.value: 0 for s in AttentionState}

        for student in self.students.values():
            state_counts[student.state.value] += 1
            ratio = student.on_task_ratio(now, cfg.window_seconds, cfg.desk_work_weight)
            if ratio is not None:
                ratios.append(ratio)

        tracked = len(ratios)
        mean_ratio = sum(ratios) / tracked if tracked else 0.0

        return {
            "on_task_ratio":     round(mean_ratio, 4),
            "class_engagement":  round(mean_ratio * 100, 1),
            "tracked_count":     tracked,
            "student_count":     len(self.students),
            "expected_count":    expected_count,
            "below_floor_count": sum(1 for r in ratios if r < cfg.on_task_floor),
            "engaged_count":     sum(1 for r in ratios if r >= cfg.on_task_floor),
            "state_counts":      state_counts,
            "is_calibrating":    self.is_calibrating,
        }


def _ema(previous: Optional[float], value: float, alpha: float) -> float:
    return value if previous is None else alpha * value + (1.0 - alpha) * previous
