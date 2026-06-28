from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import (
    create_lesson,
    get_lesson,
    get_lessons,
    load_lesson_content,
    save_lesson_content,
    update_lesson,
    update_lesson_status,
)
from ...kb.database import get_session
from ...kb.models import Lesson
from ...planner.planner import Planner

router = APIRouter(prefix="/lessons", tags=["lessons"])


class LessonCreate(BaseModel):
    topic: str
    lesson_type: str = "PlannedLesson"
    learning_path_id: Optional[int] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    duration_minutes: Optional[int] = None
    objectives: Optional[str] = None
    source: Optional[str] = None
    evidence_type: Optional[str] = None
    evidence_date: Optional[date] = None
    content: Optional[str] = None


class LessonStatusUpdate(BaseModel):
    status: str
    completed_date: Optional[date] = None


@router.post("/", response_model=Lesson, status_code=201)
def create(body: LessonCreate, session: Session = Depends(get_session)):
    data = body.model_dump()
    content = data.pop("content")
    return create_lesson(session, content=content, **data)


@router.get("/", response_model=list[Lesson])
def list_all(
    learning_path_id: Optional[int] = None,
    status: Optional[str] = None,
    lesson_type: Optional[str] = None,
    session: Session = Depends(get_session),
):
    return get_lessons(session, learning_path_id=learning_path_id, status=status, lesson_type=lesson_type)


@router.get("/{lesson_id}", response_model=Lesson)
def read(lesson_id: int, session: Session = Depends(get_session)):
    lesson = get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return lesson


@router.get("/{lesson_id}/content")
def read_content(lesson_id: int, session: Session = Depends(get_session)):
    if not get_lesson(session, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found.")
    content = load_lesson_content(lesson_id)
    return {"lesson_id": lesson_id, "content": content}


@router.put("/{lesson_id}/content")
def write_content(lesson_id: int, body: dict, session: Session = Depends(get_session)):
    if not get_lesson(session, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found.")
    save_lesson_content(lesson_id, body.get("content", ""))
    return {"lesson_id": lesson_id, "saved": True}


@router.patch("/{lesson_id}/status", response_model=Lesson)
def patch_status(lesson_id: int, body: LessonStatusUpdate, session: Session = Depends(get_session)):
    updated = update_lesson_status(session, lesson_id, body.status, body.completed_date)
    if not updated:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return updated


@router.post("/{lesson_id}/complete")
def complete_lesson(lesson_id: int, session: Session = Depends(get_session)):
    """Mark lesson completed and immediately generate its review."""
    lesson = update_lesson_status(session, lesson_id, "Completed", date.today())
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    review, content = Planner(session).generate_review(lesson_id)
    return {
        "lesson_id": lesson_id,
        "status": "Completed",
        "review_id": review.review_id,
        "review_type": review.review_type,
        "review_content": content,
    }
