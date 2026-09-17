from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...db.repositories.session_repo import SessionRepository
from ...schemas.session import SessionCreate, SessionResponse
from ..security import require_api_key

router = APIRouter()


@router.post("/", response_model=SessionResponse, status_code=201, dependencies=[Depends(require_api_key)])
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start a new monitoring session for a classroom."""
    repo    = SessionRepository(db)
    session = await repo.create(payload)
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    repo    = SessionRepository(db)
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}/end", response_model=SessionResponse, dependencies=[Depends(require_api_key)])
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark a session as ended and record its end time."""
    repo    = SessionRepository(db)
    session = await repo.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
