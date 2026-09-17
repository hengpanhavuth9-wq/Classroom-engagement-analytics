# ReLi — Agent Guide

## Project

Monorepo (backend/ frontend/ infra/) for real-time, privacy-preserving classroom engagement analytics using computer vision.

**Scope: gaze only.** Emotion and yawn detection were removed. Engagement means where a student is looking, measured as head pose relative to that student's own calibrated "looking at the board" reference.

## Commands

| Context | Command | Notes |
|---------|---------|-------|
| Backend | `uvicorn app.main:app --reload` | Run from backend/ |
| Backend | `pytest tests/ -v` | Unit tests (pytest-asyncio) |
| Backend | `python scripts/fetch_models.py` | Fetch weights — required once per clone |
| Eval | `python eval/run_eval.py <video> <annotations.csv>` | Offline accuracy against ground truth |
| Eval | `python eval/prepare_annotations.py <video> --out annotations/lesson1` | Build an annotation job |
| Eval | `python eval/agreement.py <a.csv> <b.csv>` | Cohen's kappa between annotators |
| Frontend | `npm run dev` | Next.js 14 dev server |
| Frontend | `npm run lint` | ESLint (next lint) |
| Frontend | `npm run build` | TypeScript check included |
| Full stack | `docker compose up -d` | From infra/ |

## Dev quirk — no Redis server needed

Set `REDIS_URL=memory://` in backend/.env and the backend falls back to `InMemoryRedis` (dict + asyncio queues). No external Redis required for development.

## Database

- Tables auto-created on startup via `SQLModel.metadata.create_all` in `init_db()` — no migration tool runs in practice (Alembic is a dependency but unused; no `alembic/` directory exists).
- A SQLite file `reli_dev.db` is present — the async driver for SQLite is `aiosqlite`. Postgres uses `asyncpg`.
- Set `DATABASE_URL=sqlite:///reli_dev.db` for zero-dependency local dev.

## AI model files — must be present or auto-downloaded

Weights are gitignored. Run `python scripts/fetch_models.py` once per clone.

| Model | Path | Download |
|-------|------|----------|
| MediaPipe FaceLandmarker | `backend/app/pipeline/face_landmarker.task` | **Auto-downloads** (~6 MB) on first run |
| YuNet face detector | `backend/models/face-detection/face_detection_yunet_2023mar.onnx` | `fetch_models.py`, from opencv_zoo (~230 KB) |
| Eye gaze ONNX | `backend/models/gaze-estimation/weights/resnet34_gaze.onnx` | `fetch_models.py`, from [yakhyo/gaze-estimation](https://github.com/yakhyo/gaze-estimation) |
| 6DRepNet360 head pose (opt-in, `HEAD_POSE_BACKEND=sixdrepnet`) | `backend/app/pipeline/weights/sixdrepnet360_Nx3x224x224.onnx` | `fetch_models.py --with-sixdrepnet` only — not in the default set (90 MB, unverified against this project's footage) |

Models are lazy-loaded behind a lock (the worker pool hits the loaders concurrently on the first frame), and a load failure is cached rather than retried per face. A missing gaze model degrades to head pose only — it never falls back to scoring students as engaged.

## Auth

Every REST write and both WebSockets require `Authorization: Bearer <SECRET_KEY>` / `?token=<SECRET_KEY>` respectively — see `backend/app/api/security.py`. A shared placeholder token, not per-account auth. Frontend reads it from `NEXT_PUBLIC_API_TOKEN`.

## Architecture

- **Backend entrypoint**: `backend/app/main.py` — FastAPI app with lifespan handlers (init Redis, init DB).
- **REST routers**: `/api/sessions/`, `/api/classrooms/`, `/api/analytics/` — CRUD on sessions/classrooms/metrics.
- **WebSocket routers**: `/ws/video/{session_id}` (receives JPEG frames from camera client), `/ws/dashboard/{session_id}` (pushes aggregated metrics to frontend).
- **AI pipeline**: `FrameDistributor.process_frame()` in `backend/app/pipeline/frame_distributor.py` orchestrates YuNet detection → IoU tracker → per-face MediaPipe crop → head pose from the transformation matrix → ONNX eye gaze (above the pixel gate, round-robin budget) → `AttentionEngine`. All in-memory; frames are `del` after processing. One `FrameDistributor` per session — the tracker, calibration and history are session state; the heavy models behind it are process-wide singletons.
- **Metric flow**: WebSocket → Redis pub/sub → `metric_writer` background task persists to PostgreSQL every `METRIC_WRITE_INTERVAL` seconds.
- **Alerts**: `check_and_fire_alerts()` fires on Redis pub/sub when `class_engagement < ALERT_THRESHOLD`; cooldown key prevents spam.

## Frontend

- Next.js 14 App Router (`/`, `/teacher`, `/admin`).
- **Demo mode available**: `SessionSetup` offers "Demo Mode" that simulates metrics client-side without any backend — useful for UI development.
- The `CameraClient` (`frontend/src/lib/cameraClient.ts`) captures at the camera's real resolution (1080p by default), 2 FPS, JPEG quality 0.8, over WebSocket to `/ws/video/{session_id}`. `calibrate()` sends `{"action":"calibrate"}` to start the per-student reference capture. A pipeline error/unauthorized close from the backend surfaces via an `onPipelineError` callback rather than leaving the "Camera + AI active" badge lying.
- Dashboard components are on the current gaze-only payload (`on_task_ratio`, `state_counts`, …) end to end, including persistence (`AggregatedEngagementMetric`).
- Store: Zustand (`useEngagementStore`) holds metrics, history (rolling 60 items), alerts, connection state.

## Testing quirks

- Five test files in `backend/tests/`: `test_head_pose.py`, `test_tracker.py`, `test_attention_engine.py`, `test_frame_distributor.py`, `test_eval_tuning.py`.
- Pure unit tests — no DB, no Redis, no model weights. The distributor tests stub the detector and `_analyse_face`.
- No frontend tests exist.

## Attention model

Per student, per frame, from head pose relative to their own calibrated reference:

| State | Condition | Counts as |
|---|---|---|
| `on_task` | yaw deviation from own reference < threshold | engaged |
| `desk_work` | pitch below reference by more than phi, yaw within threshold | weighted by `DESK_WORK_WEIGHT` |
| `off_task` | yaw deviation beyond threshold | not engaged |
| `unknown` | no pose, or face below `MIN_FACE_PX` | excluded from both numerator and denominator |

Reported per student as an on-task **ratio over a rolling window**, aggregated to a class mean plus the count below `ONTASK_FLOOR` (a plain mean hides a disengaged minority) plus an explicit coverage count.

Every threshold lives in `backend/app/config.py` and is marked `TODO: assumed` until `eval/` has fitted it against annotated footage. Hysteresis uses separate enter/exit thresholds so borderline students do not flap.

## Deployment

- `infra/docker-compose.yml` is the dev stack (builds images locally, volume-mounts backend for hot reload, exposes ports).
- `infra/docker-compose.prod.yml` is the production stack (pre-built images, nginx reverse proxy with TLS, persistent Redis + Postgres volumes).
- no deploy scripts, CI, or Terraform found.
