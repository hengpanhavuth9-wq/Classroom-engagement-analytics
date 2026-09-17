from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """
    Application settings.

    Every threshold in the "Attention model" block below is currently an
    assumption. `eval/sweep.py` fits them against annotated ground truth and
    `eval/tune_from_feedback.py` refits them against teacher segment ratings;
    until one of those has been run, treat the values here as placeholders.

    A fitted run writes a small YAML of just the tuned fields. Point
    `ATTENTION_CONFIG_PATH` at it (e.g. `eval/configs/tuned.yaml`) to load it
    over these defaults at startup, so a refit ships as data with no code edit.
    """

    DATABASE_URL:          str   = "postgresql://reli:secret@localhost:5432/reli_db"
    REDIS_URL:             str   = "redis://localhost:6379"
    SECRET_KEY:            str   = "dev-secret-key-replace-in-production"
    MAX_FACES_PER_CAMERA:  int   = 40
    METRIC_WRITE_INTERVAL: int   = 30
    ALERT_THRESHOLD:       float = 50.0
    ALERT_COOLDOWN:        int   = 120
    CORS_ORIGINS:          List[str] = ["http://localhost:3000"]

    # ── Detection ──────────────────────────────────────────────────────────────
    YUNET_MODEL_PATH:      str   = "models/face-detection/face_detection_yunet_2023mar.onnx"
    YUNET_SCORE_THRESHOLD: float = 0.6      # TODO: assumed — sweep on the annotated set
    YUNET_NMS_THRESHOLD:   float = 0.3      # TODO: assumed — sweep on the annotated set
    DETECT_TILING:         bool  = False    # enable only if back-row recall measures poorly
    DETECT_TILE_OVERLAP:   float = 0.2      # TODO: assumed — only used when tiling is on

    # ── Head pose ──────────────────────────────────────────────────────────────
    # "mediapipe" (default) repurposes FaceLandmarker's transformation matrix
    # (a model trained for landmarks, not pose). "sixdrepnet" is a model
    # trained specifically for full-range head pose (thohemp/6DRepNet360) —
    # plausibly more robust at classroom-back-row crop sizes, but unverified
    # against this project's actual camera/distance. Switch and re-run
    # eval/run_eval.py before trusting it over the default; see
    # ENGAGEMENT-MODEL-DECISIONS.md §4.
    HEAD_POSE_BACKEND:      str   = "mediapipe"  # "mediapipe" | "sixdrepnet"
    SIXDREPNET_CROP_MARGIN: float = 0.1          # matches the reference ONNX demo's crop convention
    SIXDREPNET_YAW_SIGN:    float = 1.0          # TODO: unverified — see GAZE_YAW_SIGN note
    SIXDREPNET_PITCH_SIGN:  float = 1.0          # TODO: unverified — same check, pitch axis

    # ── Gaze model ───────────────────────────────────────────────────────────
    GAZE_BACKBONE:         str   = "resnet34"
    MIN_FACE_PX:           int   = 24       # TODO: assumed — below this a face is `unknown`
    MIN_FACE_PX_FOR_GAZE:  int   = 80       # TODO: assumed — below this, head pose only
    GAZE_CROP_MARGIN:      float = 0.28     # TODO: assumed — model trained on margined crops
    GAZE_BLEND_WEIGHT:     float = 0.3      # TODO: assumed — fit blend on the annotated set
    GAZE_YAW_SIGN:         float = 1.0      # TODO: unverified — flip to -1.0 if verify_pose_signs.py shows gaze disagrees with head pose
    GAZE_PITCH_SIGN:       float = 1.0      # TODO: unverified — same check, pitch axis

    # ── Throughput ───────────────────────────────────────────────────────────
    # Head pose runs for every face every frame; eye gaze is a refinement, so
    # only this many faces per frame get it, round-robin by track. That keeps
    # frame cost flat as the class grows instead of scaling with student count.
    GAZE_REFRESH_BUDGET:   int   = 6        # TODO: assumed — raise if the demo machine has headroom
    PIPELINE_WORKERS:      int   = 4
    ONNX_INTRA_OP_THREADS: int   = 4

    # ── Attention model ────────────────────────────────────────────────────────
    ATTENTION_YAW_ENTER_DEG: float = 25.0   # TODO: assumed (theta) — sweep
    ATTENTION_YAW_EXIT_DEG:  float = 32.0   # TODO: assumed — hysteresis, must exceed ENTER
    DESK_WORK_PITCH_DEG:     float = 18.0   # TODO: assumed (phi) — sweep
    DESK_WORK_WEIGHT:        float = 1.0    # TODO: assumed — teacher feedback decides this
    EMA_ALPHA:               float = 0.4    # TODO: assumed — sweep
    ONTASK_WINDOW_SECONDS:   float = 20.0   # TODO: assumed — sweep
    ONTASK_FLOOR:            float = 0.5    # TODO: assumed — "below floor" = struggling
    CALIBRATION_SECONDS:     float = 5.0    # TODO: assumed — 5s of "look at the board"
    ATTENTION_CONFIG_PATH:   str   = ""     # YAML from eval/sweep.py or tune_from_feedback.py; empty = defaults above

    # ── Tracking ───────────────────────────────────────────────────────────
    TRACK_IOU_THRESHOLD:     float = 0.3    # TODO: assumed — seated students move little
    TRACK_MAX_LOST_FRAMES:   int   = 15     # TODO: assumed — ~7s of tolerance at 2 FPS

    class Config:
        env_file = ".env"


settings = Settings()
