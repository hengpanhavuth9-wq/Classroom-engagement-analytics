import json
import redis.asyncio as aioredis

from ..config import settings
from .redis_service import session_channel


async def check_and_fire_alerts(
    redis: aioredis.Redis,
    session_id: str,
    metrics: dict,
) -> None:
    """
    Fire a low_engagement alert when class engagement drops below threshold.
    A cooldown key prevents alert spam: only fires once per ALERT_COOLDOWN seconds.

    Published on the same channel the dashboard already subscribes to for
    metrics (`session_channel`) — a separate `alerts:{id}` channel used to
    exist here with nothing ever subscribed to it, so alerts were silently
    dropped. The frontend tells the two apart by `type: "low_engagement"`,
    which a metrics payload never has.

    Requires at least one tracked student: with zero tracked, class_engagement
    is 0.0 by construction (engagement_engine.class_metrics), which is not a
    real "the class is disengaged" reading — it means nobody has enough
    calibrated history yet (session just started, or between calibrations).
    """
    tracked = metrics.get("tracked_count", 0)
    if tracked == 0:
        return

    score     = metrics.get("class_engagement", 100.0)
    alert_key = f"alert:{session_id}:low_engagement"

    if score < settings.ALERT_THRESHOLD:
        already_alerted = await redis.get(alert_key)
        if not already_alerted:
            alert = {
                "type":       "low_engagement",
                "session_id": session_id,
                "score":      score,
                "message":    f"⚠️ Class engagement dropped to {score:.0f}%",
            }
            await redis.publish(session_channel(session_id), json.dumps(alert))
            await redis.setex(alert_key, settings.ALERT_COOLDOWN, "1")
