from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import create_learning_path, get_learning_paths, get_user, update_learning_path
from ...kb.database import get_session
from ...kb.models import LearningPath

router = APIRouter(prefix="/learning-paths", tags=["learning_paths"])


class LearningPathCreate(BaseModel):
    title: str
    status: str = "Active"


class LearningPathUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


def _require_user(session: Session):
    user = get_user(session)
    if not user:
        raise HTTPException(status_code=404, detail="No user found. Create a user first.")
    return user


@router.post("/", response_model=LearningPath, status_code=201)
def create(body: LearningPathCreate, session: Session = Depends(get_session)):
    user = _require_user(session)
    return create_learning_path(session, user.user_id, body.title, body.status)


@router.get("/", response_model=list[LearningPath])
def list_all(session: Session = Depends(get_session)):
    user = _require_user(session)
    return get_learning_paths(session, user.user_id)


@router.patch("/{path_id}", response_model=LearningPath)
def patch(path_id: int, body: LearningPathUpdate, session: Session = Depends(get_session)):
    updated = update_learning_path(
        session, path_id, **{k: v for k, v in body.model_dump().items() if v is not None}
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Learning path not found.")
    return updated
