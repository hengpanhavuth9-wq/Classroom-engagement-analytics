"""
Minimal shared-secret guard.

This is a placeholder, not real auth: one token shared by every teacher,
configured via `SECRET_KEY`, checked with a plain string comparison. It
exists because nothing previously required credentials at all — anyone who
could reach the backend could watch any classroom's live per-face overlay,
push arbitrary video into a session, or overwrite another session's teacher
ratings. A real deployment needs per-teacher accounts (JWT or session
cookies) and per-classroom authorization, not a single global token.
"""
import hmac

from fastapi import Header, HTTPException, WebSocket

from ..config import settings


def _matches(candidate: str | None) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(candidate, settings.SECRET_KEY)


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency for mutating REST routes: `Authorization: Bearer <SECRET_KEY>`."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not _matches(token):
        raise HTTPException(status_code=401, detail="missing or invalid API key")


def websocket_authorized(websocket: WebSocket) -> bool:
    """For the video/dashboard sockets: `?token=<SECRET_KEY>` query param.

    A query param, not a header, because the browser WebSocket API cannot set
    custom headers on the handshake request.
    """
    return _matches(websocket.query_params.get("token"))
