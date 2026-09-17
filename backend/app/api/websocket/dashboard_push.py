from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...services.redis_service import subscribe_metrics, get_latest_metrics, get_redis
from ..security import websocket_authorized

router = APIRouter()


@router.websocket("/ws/dashboard/{session_id}")
async def dashboard_stream(websocket: WebSocket, session_id: str):
    """
    Pushes live engagement metrics to the Next.js teacher dashboard.
    The dashboard client receives only anonymous aggregated class data.
    """
    if not websocket_authorized(websocket):
        await websocket.close(code=4401)
        return

    await websocket.accept()

    # Send the most recent cached snapshot immediately (avoids blank screen on connect)
    redis  = await get_redis()
    cached = await get_latest_metrics(redis, session_id)
    if cached:
        import json
        await websocket.send_text(json.dumps(cached))

    try:
        async for metrics_json in subscribe_metrics(session_id):
            await websocket.send_text(metrics_json)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[dashboard_push] Error: {exc}")
