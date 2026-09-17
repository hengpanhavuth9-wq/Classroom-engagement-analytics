import asyncio
import json
import logging

from ..db.database import AsyncSessionLocal
from ..db.models import AggregatedEngagementMetric
from ..db.repositories.session_repo import SessionRepository
from ..services.redis_service import get_redis
from ..config import settings

logger = logging.getLogger(__name__)


async def periodic_metric_writer() -> None:
    """
    Background task: every METRIC_WRITE_INTERVAL seconds, snapshot each
    active session's latest Redis metrics into Postgres/SQLite.

    Active sessions are read from the DB (Session.is_active) rather than a
    passed-in set, so this task needs no wiring from the websocket layer and
    can't silently drift out of sync with what `/api/sessions` considers
    active. Only anonymous, class-level data is written — no per-student data
    and no raw video ever reaches this table.

    Started from `main.py`'s lifespan; cancelled on shutdown.
    """
    redis = await get_redis()
    while True:
        await asyncio.sleep(settings.METRIC_WRITE_INTERVAL)
        try:
            await _write_snapshot(redis)
        except Exception:
            logger.exception("[metric_writer] snapshot failed — will retry next interval")


async def _write_snapshot(redis) -> None:
    async with AsyncSessionLocal() as db:
        active = await SessionRepository(db).list_active()
        if not active:
            return
        for session in active:
            raw = await redis.get(f"session:{session.id}:live")
            if not raw:
                continue
            m = json.loads(raw)
            # A session with no tracked students yet (still calibrating, or no
            # camera connected) has nothing meaningful to persist.
            if m.get("tracked_count", 0) == 0:
                continue
            counts = m.get("state_counts", {})
            db.add(AggregatedEngagementMetric(
                session_id        =session.id,
                on_task_ratio     =m.get("on_task_ratio", 0.0),
                class_engagement  =m.get("class_engagement", 0.0),
                student_count     =m.get("student_count", 0),
                tracked_count     =m.get("tracked_count", 0),
                engaged_count     =m.get("engaged_count", 0),
                below_floor_count =m.get("below_floor_count", 0),
                on_task_count     =counts.get("on_task", 0),
                desk_work_count   =counts.get("desk_work", 0),
                off_task_count    =counts.get("off_task", 0),
                unknown_count     =counts.get("unknown", 0),
            ))
        await db.commit()
