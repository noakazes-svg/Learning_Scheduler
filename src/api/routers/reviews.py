from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import (
    create_review,
    create_review_result,
    get_lesson,
    get_review_results,
    get_reviews,
)
from ...kb.database import get_session
from ...kb.models import Review, ReviewResult

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewCreate(BaseModel):
    lesson_id: int
    review_type: str   # Quiz | Project | Exercise | Assessment
    due_date: Optional[date] = None


class ReviewResultCreate(BaseModel):
    score: Optional[float] = None
    max_score: Optional[float] = None
    passed: Optional[bool] = None
    feedback: Optional[str] = None


@router.post("/", response_model=Review, status_code=201)
def create(body: ReviewCreate, session: Session = Depends(get_session)):
    if not get_lesson(session, body.lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return create_review(session, body.lesson_id, body.review_type, body.due_date)


@router.get("/", response_model=list[Review])
def list_for_lesson(lesson_id: int, session: Session = Depends(get_session)):
    return get_reviews(session, lesson_id)


@router.post("/{review_id}/results", response_model=ReviewResult, status_code=201)
def submit_result(review_id: int, body: ReviewResultCreate, session: Session = Depends(get_session)):
    return create_review_result(session, review_id, **body.model_dump())


@router.get("/{review_id}/results", response_model=list[ReviewResult])
def list_results(review_id: int, session: Session = Depends(get_session)):
    return get_review_results(session, review_id)
