import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...config import settings
from ...services.alert_service import check_and_fire_alerts
from ...services.redis_service import get_redis, publish_metrics
from ..security import websocket_authorized

router = APIRouter()


def _build_distributor():
    """
    One pipeline per session: the tracker, per-session calibration and
    attention history are session state and must not be shared between rooms.
    The heavy models behind it are process-wide singletons, so this is cheap.
    """
    from ...pipeline.frame_distributor import FrameDistributor
    return FrameDistributor(max_faces=settings.MAX_FACES_PER_CAMERA)


@router.websocket("/ws/video/{session_id}")
async def video_stream(websocket: WebSocket, session_id: str):
    """
    Receives JPEG frames from the classroom camera client, runs the gaze-only
    pipeline, and publishes ONLY anonymous aggregated metrics.

    Control messages (JSON text frames) drive calibration:
        {"action": "calibrate"} — start the "everyone look at the board" window

    BACKPRESSURE: a reader task keeps only the most recently received frame;
    the processing loop always works on whatever is newest. A frame that
    arrives while the previous one is still processing is dropped rather than
    queued — attention is read over a multi-second window, so a skipped frame
    costs nothing, but an unbounded queue means the dashboard falls further
    behind the room with every frame it can't keep up with. (The previous
    `if processing: continue` guard never actually triggered: the loop
    `await`ed `process_frame` before it next called `receive()`, so it was
    never busy at the point the check ran.)

    PRIVACY GUARANTEE:
        - Frames are decoded in RAM as numpy arrays and released after use.
        - Raw video NEVER touches the filesystem or an external service.
        - The published payload carries class aggregates plus this frame's
          geometry — no identifiers, and nothing that links a face across frames.
    """
    if not websocket_authorized(websocket):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    redis = await get_redis()

    try:
        distributor = _build_distributor()
    except Exception as exc:
        await websocket.send_text(json.dumps({
            "error": f"AI pipeline unavailable: {exc}",
            "hint": "Run: python scripts/fetch_models.py",
        }))
        await websocket.close()
        return

    import cv2
    import numpy as np

    inbox: dict = {}
    new_message = asyncio.Event()
    calibration_ends_at: float | None = None

    async def reader() -> None:
        """Pull frames off the socket as fast as they arrive; never processes
        one itself, so a slow pipeline never makes this loop fall behind."""
        while True:
            message = await websocket.receive()
            if message.get("text") is not None:
                inbox["text"] = message["text"]
            elif message.get("bytes"):
                inbox["frame"] = message["bytes"]  # overwrite = drop the stale one
            else:
                continue
            new_message.set()

    reader_task = asyncio.create_task(reader())

    try:
        while True:
            await new_message.wait()
            new_message.clear()

            text = inbox.pop("text", None)
            if text is not None:
                calibration_ends_at = _handle_control(text, distributor, calibration_ends_at)

            raw_bytes = inbox.pop("frame", None)
            if raw_bytes is None:
                continue

            frame_array = np.frombuffer(raw_bytes, dtype=np.uint8)
            frame_bgr = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            if frame_bgr is None:
                continue

            now = time.monotonic()
            if calibration_ends_at is not None and now >= calibration_ends_at:
                calibrated = distributor.finish_calibration()
                calibration_ends_at = None
                print(f"[video_receiver] calibrated {calibrated} students in {session_id}")

            observations = await distributor.process_frame(frame_bgr, now)
            metrics = distributor.aggregate_class_metrics(observations, now)
            metrics["session_id"] = session_id

            # ── PRIVACY BOUNDARY: only the metrics dict crosses this line ──
            await publish_metrics(redis, session_id, metrics)
            await check_and_fire_alerts(redis, session_id, metrics)

            del frame_bgr, frame_array

    except (WebSocketDisconnect, RuntimeError):
        print(f"[video_receiver] Camera disconnected: session {session_id}")
    except Exception as exc:
        print(f"[video_receiver] Error in session {session_id}: {exc}")
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            pass


def _handle_control(text: str, distributor, calibration_ends_at):
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return calibration_ends_at
    if payload.get("action") == "calibrate":
        now = time.monotonic()
        distributor.start_calibration(now)
        print("[video_receiver] calibration started")
        return now + distributor.config.calibration_seconds
    return calibration_ends_at
