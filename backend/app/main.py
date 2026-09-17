import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager

from .config import settings
from .api.routes import sessions, classrooms, analytics, feedback
from .api.websocket import video_receiver, dashboard_push
from .services.redis_service import init_redis, close_redis
from .services.metric_writer import periodic_metric_writer
from .db.database import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle manager."""
    await init_redis()
    await init_db()
    writer_task = asyncio.create_task(periodic_metric_writer())
    yield
    writer_task.cancel()
    try:
        await writer_task
    except asyncio.CancelledError:
        pass
    await close_redis()


app = FastAPI(
    title="ReLi Engagement API",
    description="Real-time, privacy-preserving classroom engagement analytics.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(sessions.router,   prefix="/api/sessions",   tags=["Sessions"])
app.include_router(classrooms.router, prefix="/api/classrooms", tags=["Classrooms"])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"])
app.include_router(feedback.router,   prefix="/api/eval",       tags=["Eval"])

# WebSocket routers
app.include_router(video_receiver.router)
app.include_router(dashboard_push.router)


@app.get("/", include_in_schema=False)
async def root():
    # The API has no page of its own; opening the bare URL used to 404.
    return RedirectResponse("/docs")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "reli-backend"}
