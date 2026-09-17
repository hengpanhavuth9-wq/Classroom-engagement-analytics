from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from ...db.database import get_db
from ...db.models import Classroom
from ..security import require_api_key

router = APIRouter()


class ClassroomCreate(BaseModel):
    name:        str
    school_name: str
    capacity:    int = 30


class ClassroomResponse(BaseModel):
    id:          str
    name:        str
    school_name: str
    capacity:    int

    class Config:
        from_attributes = True


@router.post("/", response_model=ClassroomResponse, status_code=201, dependencies=[Depends(require_api_key)])
async def create_classroom(
    payload: ClassroomCreate,
    db: AsyncSession = Depends(get_db),
):
    classroom = Classroom(**payload.model_dump())
    db.add(classroom)
    await db.commit()
    await db.refresh(classroom)
    return classroom


@router.get("/", response_model=list[ClassroomResponse])
async def list_classrooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Classroom))
    return result.scalars().all()


@router.get("/{classroom_id}", response_model=ClassroomResponse)
async def get_classroom(
    classroom_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Classroom).where(Classroom.id == classroom_id)
    )
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    return classroom
