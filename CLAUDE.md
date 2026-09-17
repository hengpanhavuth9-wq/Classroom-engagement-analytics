# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ReLi — real-time, privacy-preserving classroom engagement analytics. Monorepo: `backend/` (FastAPI + CV pipeline), `frontend/` (Next.js 14 App Router), `infra/` (Docker Compose + nginx).

**Scope: gaze only.** Emotion and yawn detection were removed. Engagement is defined by where a student is looking, measured as head pose relative to that student's own calibrated "looking at the board" reference. See `ENGAGEMENT-MODEL-DECISIONS.md` and the recovery plan for why.

## Commands

| Task | Command | Notes |
|---|---|---|
| Backend dev server | `uvicorn app.main:app --reload` | Run from `backend/` |
| Backend tests | `pytest tests/ -v` | Must run from `backend/` — `tests/__init__.py` makes pytest put `backend/` on `sys.path` so `from app.…` resolves. There is no pytest config file. |
| Single test | `pytest tests/test_attention_engine.py::test_calibration_cancels_seat_position -v` | |
| Fetch model weights | `python scripts/fetch_models.py` | Required once per clone; weights are gitignored |
| Offline accuracy eval | `python eval/run_eval.py <video> <annotations.csv> --out eval/out/r.json` | From `backend/`. Needs a recording + labels |
| Prepare an annotation job | `python eval/prepare_annotations.py <video> --out annotations/lesson1` | Samples frames, pre-fills detected boxes |
| Inter-annotator agreement | `python eval/agreement.py <a.csv> <b.csv>` | Cohen's kappa |
| Frontend dev | `npm run dev` | From `frontend/` |
| Frontend lint | `npm run lint` | `next lint` |
| Frontend typecheck | `npm run build` | No standalone `tsc` script; build is the typecheck |
| Full stack | `docker compose up -d` | From `infra/` |

No CI, deploy scripts, or migration tooling exist. `alembic` is in `requirements.txt` but there is no `alembic/` directory — tables are created at startup by `SQLModel.metadata.create_all` in [init_db()](backend/app/db/database.py#L36).

## Zero-dependency local dev

`backend/.env` (already present, gitignored) is set up so neither Redis nor Postgres is needed:

- `REDIS_URL=memory://` → [redis_service.init_redis()](backend/app/services/redis_service.py#L10) swaps in `InMemoryRedis` (dict + asyncio queues). It also falls back to this automatically if a real Redis is unreachable.
- `DATABASE_URL=sqlite:///reli_dev.db` → [_build_async_url()](backend/app/db/database.py#L7) rewrites drivers (`sqlite`→`aiosqlite`, `postgresql`→`asyncpg`).
- `CORS_ORIGINS` is parsed as JSON by pydantic-settings, so it must be written as `["http://localhost:3000"]`.

Frontend has a **Demo Mode** (button in [SessionSetup](frontend/src/components/ui/SessionSetup.tsx)) that simulates metrics client-side via `makeDemoMetrics()` in [teacher/page.tsx](frontend/src/app/teacher/page.tsx#L21) — full dashboard UI with no backend at all.

## Data flow

```
Camera (CameraClient, 2 FPS, full-resolution JPEG q=0.8)
  → WS /ws/video/{session_id}   [video_receiver.py]
  → FrameDistributor.process_frame()  ── PRIVACY BOUNDARY ──
  → aggregate_class_metrics()  → metrics dict only
  → Redis SETEX session:{id}:live  +  PUBLISH channel:session:{id}
  → WS /ws/dashboard/{session_id}  [dashboard_push.py]
  → Zustand useEngagementStore (rolling 60-item history)
```

The pipeline ([frame_distributor.py](backend/app/pipeline/frame_distributor.py)):

```
YuNet (full frame) → tracker → per-face crop → MediaPipe FaceLandmarker
                                             → head pose (4x4 transform matrix)
                                             → eye gaze ONNX  [only above
                                                MIN_FACE_PX_FOR_GAZE, and only
                                                GAZE_REFRESH_BUDGET faces per
                                                frame, round-robin]
                             → AttentionEngine (calibration, EMA, hysteresis,
                                                rolling on-task ratio)
```

One detector, one face list. Head pose is the primary signal because at classroom distance the iris is 2-3 px and eye gaze is not recoverable; eye gaze refines the front rows only. The gaze refresh budget keeps per-frame cost flat as the class grows — 40 students costs the same as 20.

Per-student states are `on_task` / `desk_work` / `off_task` / `unknown`. `unknown` is excluded from both numerator and denominator and surfaced as a coverage figure — never scored as engaged.

**Privacy invariant** — frames live only as numpy arrays in RAM and are `del`'d after processing; only the aggregated dict crosses to Redis/DB. Per-face data that does leave is geometry-only (normalized bbox, yaw/pitch, emotion label) for the camera overlay — no identifiers. Keep this property when touching `video_receiver.py`, `aggregate_class_metrics`, or the DB models.

## Model weights

Heavy models are lazy-loaded (`_get_gaze_model()`, `_get_emotion_model()`), so the server and the WS endpoint start even when weights are missing — the pipeline just degrades (gaze defaults to "looking", emotion to cached/0.6).

Weights are gitignored, not vendored. Run `python scripts/fetch_models.py` once per clone.

| Model | Path | Source |
|---|---|---|
| MediaPipe FaceLandmarker | `backend/app/pipeline/face_landmarker.task` | Auto-downloads (~6 MB) on first use |
| YuNet face detector | `backend/models/face-detection/face_detection_yunet_2023mar.onnx` | opencv_zoo (~230 KB). `cv2.FaceDetectorYN` ships inside OpenCV, so no extra Python dependency |
| Eye gaze ONNX | `backend/models/gaze-estimation/weights/resnet34_gaze.onnx` | [yakhyo/gaze-estimation](https://github.com/yakhyo/gaze-estimation) releases. `resnet18_gaze.onnx` is also fetched as a faster fallback |

Both ONNX models are lazy-loaded and a load failure is cached, not retried per face. When the gaze model is missing the pipeline runs on head pose alone and says so — it does **not** fall back to scoring students as engaged.

## Auth

Every route and both WebSockets require a shared bearer token (see
`backend/app/api/security.py`), checked against `SECRET_KEY`: REST via
`Authorization: Bearer <token>` (`Depends(require_api_key)` on mutating
routes only — GETs stay open), WebSockets via `?token=<token>` (the browser
WS API can't set headers). This is a placeholder — one token for every
teacher — not real per-account auth; see the module docstring. The frontend
reads it from `NEXT_PUBLIC_API_TOKEN` (`lib/api.ts: wsToken()`); Docker Compose
wires the same value into both services' env (`infra/docker-compose.yml`).

## Optional: 6DRepNet360 head pose

`config.py: HEAD_POSE_BACKEND` defaults to `"mediapipe"`. Setting it to
`"sixdrepnet"` swaps the yaw/pitch/roll source to a dedicated head-pose model
(`pipeline/head_pose_sixdrepnet.py`, ONNX export of thohemp/6DRepNet360 via
PINTO_model_zoo) instead of repurposing FaceLandmarker's transformation
matrix. Fetch its weights with `python scripts/fetch_models.py
--with-sixdrepnet` (not in the default set — it's a 90 MB opt-in). Its own
sign convention is unverified (`SIXDREPNET_YAW_SIGN` / `SIXDREPNET_PITCH_SIGN`
in `config.py`), same as the MediaPipe path's — run `eval/verify_pose_signs.py`
against real footage before trusting either over the other; see
`ENGAGEMENT-MODEL-DECISIONS.md` §4.

## Previously known wiring gaps — now fixed

These were real dead ends; kept here so the fix is traceable, not because
they're still open:

- **Frontend/backend payload mismatch, `periodic_metric_writer` never
  started, alerts routed to a channel nobody subscribed to, `reli_dev.db`
  stale/committed** — all fixed together: the pipeline's actual gaze-only
  payload (`on_task_ratio`, `state_counts`, …) now flows end to end through
  `AggregatedEngagementMetric` (`db/models.py`), `periodic_metric_writer`
  (queries `Session.is_active` directly — no external set to wire), and
  `alert_service` (publishes on the same `session_channel()` the dashboard
  already subscribes to, and only once ≥1 student is tracked — see
  `ENGAGEMENT-MODEL-DECISIONS.md` §5 row 16). `reli_dev.db` is gitignored,
  not committed.
- **Frontend Dockerfile** now copies `.next/static` and `public` (the latter
  needed a `frontend/public/.gitkeep` — Next's standalone output expects the
  directory to exist even with nothing in it).
- **The video WebSocket's backpressure never actually dropped frames**
  (`if processing: continue` could never trigger) — replaced with a
  reader-task/latest-frame pattern in `video_receiver.py`; see its docstring.
  `cameraClient.ts`'s capture rate is back to ~2 FPS to match
  `TRACK_MAX_LOST_FRAMES` / `EMA_ALPHA` / `eval/run_eval.py`'s default, all
  tuned assuming that rate — the live preview itself is unaffected (`<video>`
  renders the stream directly; the interval only governs the analysis
  send rate).

## Frontend notes

- Path alias `@/*` → `frontend/src/*`. Tailwind + Recharts + Zustand + lucide-react. No test setup.
- API/WS base URLs come from `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_WS_URL`, defaulting to `localhost:8000`. They are baked in as Docker build args, not runtime env.
- `useEngagementSocket` auto-reconnects every 3s on close.
- `useGazeOverlay` draws bboxes and gaze arrows on a canvas layered over the `<video>` element, using the normalized `faces[]` from the metrics payload.

## Other docs in the repo

- `AGENTS.md` — shorter agent guide covering the same ground; keep the two consistent if you change one.
- `ST-analysis-upgrade-plan.md` — proposed replacement of the old score with S-T (Student-Teacher) analysis via a YOLOv8n behavioral classifier. Design doc only, parked: it needs thousands of annotated frames and contradicts the gaze-only scope.
- `backend/eval/` — offline accuracy harness. `run_eval.py` splits into an expensive extract stage (decode, detect, pose, gaze → JSONL cache) and a cheap score stage (replay through `AttentionEngine`), so threshold sweeps do not re-decode video.
- `SKILL.MD` / `.opencode/skills/frontend-design/SKILL.md` — frontend visual-design guidance skill (duplicated content).
