from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import create_user, get_user, set_target_role, update_user, upsert_competency
from ...kb.database import get_session
from ...kb.models import User

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    timezone: str


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    timezone: Optional[str] = None


@router.post("/", response_model=User, status_code=201)
def create(body: UserCreate, session: Session = Depends(get_session)):
    if get_user(session):
        raise HTTPException(status_code=409, detail="A user already exists.")
    return create_user(session, **body.model_dump())


@router.get("/me", response_model=User)
def read(session: Session = Depends(get_session)):
    user = get_user(session)
    if not user:
        raise HTTPException(status_code=404, detail="No user found.")
    return user


@router.patch("/me", response_model=User)
def patch(body: UserUpdate, session: Session = Depends(get_session)):
    user = get_user(session)
    if not user:
        raise HTTPException(status_code=404, detail="No user found.")
    updated = update_user(session, user.user_id, **{k: v for k, v in body.model_dump().items() if v is not None})
    return updated


class SelfAssessmentEntry(BaseModel):
    skill_name: str
    current_level: int
    target_level: int
    priority: Optional[str] = None
    description: Optional[str] = None


class SelfAssessmentRequest(BaseModel):
    target_role: str
    skills: list[SelfAssessmentEntry]


@router.post("/me/self-assessment")
def self_assessment(body: SelfAssessmentRequest, session: Session = Depends(get_session)):
    """Rate current skill levels and set target role. Creates or updates competencies."""
    user = get_user(session)
    if not user:
        raise HTTPException(status_code=404, detail="No user found.")
    set_target_role(session, user.user_id, body.target_role)
    saved = []
    for entry in body.skills:
        comp = upsert_competency(
            session,
            user_id=user.user_id,
            skill_name=entry.skill_name,
            current_level=entry.current_level,
            target_level=entry.target_level,
            description=entry.description,
            priority=entry.priority,
        )
        saved.append(comp.skill_name)
    return {"target_role": body.target_role, "competencies_saved": saved}
