# ReLi — Engagement Model Decisions One-Pager

Purpose: map every hardcoded constant in the attention pipeline to its
justification and evidence status, to drive the mentor discussion on survey
design and model-choice evidence.

**Rewritten for the gaze-only architecture.** Emotion and yawn detection were
removed; engagement is now measured as head pose (primary) blended with eye
gaze (refinement, front rows only), relative to each student's own calibrated
"looking at the board" reference. The previous version of this document
described the retired Haar/FER+/0.50-0.30-0.20 pipeline and should not be
used — see `CLAUDE.md` for the current data flow.

Legend: 🟢 literature-supported · 🟡 plausible but unverified · 🔴 arbitrary / chosen for convenience

---

## 1. Why relative, calibrated pose

Camera-relative yaw confounds seat position with attention: a front-left
student looking at the board has a large camera-relative yaw and would score
as distracted, while a back-row student staring at the lens would score as
attentive. Measuring deviation from each student's own calibrated reference
(`AttentionEngine.finish_calibration`, `head_pose.angular_deviation`) cancels
seat position, the camera-vs-board offset, and the pose estimator's per-subject
bias — none of which an absolute threshold can reach. 🟢 — the *reasoning* is
sound and testable; whether the calibration procedure itself is reliable
(5 s, median of ≥3 samples) is still 🟡.

## 2. Attention state thresholds

| # | Decision | Value | Where | Justification (current) | Evidence status |
|---|----------|-------|-------|-------------------------|-----------------|
| 1 | Yaw enter threshold | 25° | `config.py: ATTENTION_YAW_ENTER_DEG` | Hand-picked | 🔴 |
| 2 | Yaw exit threshold (hysteresis) | 32° | `config.py: ATTENTION_YAW_EXIT_DEG` | Must exceed enter, so borderline poses don't flap frame to frame | 🔴 |
| 3 | Desk-work pitch threshold | 18° | `config.py: DESK_WORK_PITCH_DEG` | Looking down ≠ looking away (a student reading notes is on task) | 🔴 |
| 4 | Desk-work credit weight | 1.0 (full credit) | `config.py: DESK_WORK_WEIGHT` | Assumed equal to on-task until teacher feedback says otherwise | 🔴 |
| 5 | EMA smoothing | α = 0.4 | `config.py: EMA_ALPHA` | Per-frame smoothing constant — its effective time window depends on capture FPS (`cameraClient.ts`); tuned assuming ~2 FPS | 🔴 |
| 6 | On-task rolling window | 20 s | `config.py: ONTASK_WINDOW_SECONDS` | Momentary time sampling, matching classroom-observation practice | 🟡 |
| 7 | On-task floor | 0.5 | `config.py: ONTASK_FLOOR` | Midpoint convention, for "below floor" reporting | 🔴 |
| 8 | Calibration window | 5 s, ≥3 samples, median | `config.py: CALIBRATION_SECONDS`, `AttentionEngine.finish_calibration` | Median rather than mean so one glance-away sample doesn't drag the reference off the board | 🟡 |

**All eight are marked `TODO: assumed` in `config.py` as of this writing.**
`eval/sweep.py` exists to fit them against annotated ground truth, and
`eval/tune_from_feedback.py` against teacher segment ratings (via the Review
page) — neither has been run and reported yet.

## 3. Model choices

| # | Model | Where | Why this one (current) | Evidence status |
|---|-------|-------|------------------------|-----------------|
| 9  | Face detection: YuNet (`cv2.FaceDetectorYN`) | `yunet_detector.py` | Replaced Haar — detects small/off-axis faces the classroom's back row needs; ships inside OpenCV, no extra dependency | 🟢 — published WIDER FACE hard-set numbers; unmeasured on this classroom's actual camera/distance |
| 10 | Head pose: MediaPipe FaceLandmarker's transformation matrix | `head_pose.py`, `mediapipe_init.py` | Not a dedicated pose model — repurposed from landmark fitting, which the pipeline already runs. At classroom distance the iris is 2-3 px, so a dedicated eye-only method isn't viable and head pose is the primary recoverable signal | 🟡 — the matrix's own fit quality at 40-60 px crops is unmeasured; the pitch sign convention is flagged unverified (see §4) |
| 11 | Eye gaze: yakhyo/resnet34_gaze ONNX | `gaze_onnx.py` | L2CS-style binned classification; refines only faces above `MIN_FACE_PX_FOR_GAZE` (80 px), front rows only | 🟡 — reasonable published lineage; contribution on classroom crops unmeasured, and its sign convention vs. head pose is unverified (see §4) |
| 12 | Gaze/pose blend weight | 0.3 (gaze) / 0.7 (head pose) | `config.py: GAZE_BLEND_WEIGHT`, `engagement_engine._blend` | Weighted average of two estimates of the same quantity | 🔴 |

## 4. Open correctness question: sign conventions

`head_pose.py` fixes "positive pitch = looking down" and flags it
`TODO: assumed`; `eval/verify_pose_signs.py` checks it against `desk_work` /
`on_board` / `off_board` labels and now also prints whether eye gaze agrees
with head pose on the same detections (`GAZE_YAW_SIGN` / `GAZE_PITCH_SIGN` in
`config.py`, both currently `+1.0`, unverified). **Run
`verify_pose_signs.py` against real annotated footage before tuning
anything** — if either sign is flipped, every desk_work/off_task call
inverts, or gaze fights head pose instead of refining it, and a threshold fit
on top of that is meaningless.

## 5. Class-level & alerting constants

| # | Decision | Value | Where | Justification (current) | Evidence status |
|---|----------|-------|-------|-------------------------|-----------------|
| 13 | Class engagement = mean on-task ratio, tracked students only | — | `AttentionEngine.class_metrics` | Mean, but `below_floor_count` / `tracked_count` vs `student_count` are reported alongside so a disengaged minority and a coverage gap aren't hidden inside the average | 🟡 |
| 14 | Low-engagement alert threshold | < 50.0 | `config.py: ALERT_THRESHOLD` | Round number | 🔴 |
| 15 | Alert cooldown | 120 s | `config.py: ALERT_COOLDOWN` | Arbitrary | 🔴 |
| 16 | Alert requires ≥1 tracked student | — | `alert_service.check_and_fire_alerts` | Without this, `class_engagement` is 0.0 by construction before calibration finishes (nobody has measured history yet), which fired a false "class disengaged" alert on every session start | 🟢 — this one is a correctness fix, not a tuning choice |
| 17 | Metric write interval | 30 s | `config.py: METRIC_WRITE_INTERVAL` | Persistence convenience | 🟡 |

## 6. Open questions for the mentor

1. **Scope of the survey/sweep** — validate only the yaw/pitch thresholds (row 1-3), or also the blend weight (row 12), the desk-work credit (row 4), and the smoothing/window constants (row 5-6)? Recommend: at minimum the yaw/pitch thresholds — they define what "off task" means at all.
2. **Ground truth source** — `eval/prepare_annotations.py` + `eval/agreement.py` exist for building an annotated set with inter-annotator agreement. Has one been collected yet for this classroom's actual camera and seating?
3. **How do we verify a fit is better, not just different?** `eval/run_eval.py --calibrate oracle` reports a best-case ceiling using ground-truth calibration references — compare any fitted config against that, not just against the unfitted defaults.
4. **Ethics** — classroom recordings for offline eval are gitignored (`backend/recordings/`, `backend/annotations/`) and never touch the live privacy boundary; confirm the consent/IRB status of whatever footage is used to run `eval/`.

## 7. Immediate hygiene (no research needed)

- [x] Sign convention now has a documented, config-driven flip (`GAZE_YAW_SIGN` / `GAZE_PITCH_SIGN`) instead of a silent assumption — still needs `verify_pose_signs.py` run against real footage to actually set them.
- [ ] None of rows 1-8 or 12-15 have been fit against annotated data — `eval/sweep.py` / `eval/tune_from_feedback.py` exist and are unused so far.
- [ ] `EMA_ALPHA` and `TRACK_MAX_LOST_FRAMES` (`config.py`) were tuned assuming ~2 FPS capture; confirm the deployed capture rate (`cameraClient.ts: DEFAULTS.fps`) still matches before trusting either.
