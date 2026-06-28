from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import create_user, get_user, update_user
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
