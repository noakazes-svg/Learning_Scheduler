from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ...kb.crud import (
    create_competency,
    get_competencies,
    get_competency_gaps,
    get_user,
    update_competency_level,
    upsert_competency,
)
from ...kb.database import get_session
from ...kb.models import Competency

router = APIRouter(prefix="/competencies", tags=["competencies"])


class CompetencyCreate(BaseModel):
    skill_name: str
    current_level: int = Field(ge=1, le=5)
    target_level: int = Field(ge=1, le=5)
    description: Optional[str] = None
    priority: Optional[str] = None


class CompetencyUpsert(CompetencyCreate):
    pass


class LevelUpdate(BaseModel):
    current_level: int = Field(ge=1, le=5)


def _require_user(session: Session):
    user = get_user(session)
    if not user:
        raise HTTPException(status_code=404, detail="No user found. Create a user first.")
    return user


@router.post("/", response_model=Competency, status_code=201)
def create(body: CompetencyCreate, session: Session = Depends(get_session)):
    user = _require_user(session)
    return create_competency(session, user.user_id, **body.model_dump())


@router.put("/", response_model=Competency)
def upsert(body: CompetencyUpsert, session: Session = Depends(get_session)):
    user = _require_user(session)
    return upsert_competency(session, user.user_id, **body.model_dump())


@router.get("/", response_model=list[Competency])
def list_all(session: Session = Depends(get_session)):
    user = _require_user(session)
    return get_competencies(session, user.user_id)


@router.get("/gaps", response_model=list[Competency])
def list_gaps(session: Session = Depends(get_session)):
    user = _require_user(session)
    return get_competency_gaps(session, user.user_id)


@router.patch("/{competency_id}/level", response_model=Competency)
def update_level(competency_id: int, body: LevelUpdate, session: Session = Depends(get_session)):
    updated = update_competency_level(session, competency_id, body.current_level)
    if not updated:
        raise HTTPException(status_code=404, detail="Competency not found.")
    return updated
