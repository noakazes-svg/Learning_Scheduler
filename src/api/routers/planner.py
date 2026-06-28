from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.database import get_session
from ...planner.planner import PlanningResult, ReviewContent, ReviewEvaluation, Planner

router = APIRouter(prefix="/planner", tags=["planner"])


class CycleRequest(BaseModel):
    max_topics: int = 3


class EvaluateRequest(BaseModel):
    submission: str


class CompetencyDeltaRequest(BaseModel):
    competency_id: int
    delta: int


@router.post("/cycle", response_model=PlanningResult)
def run_cycle(body: CycleRequest, session: Session = Depends(get_session)):
    try:
        return Planner(session).run_planning_cycle(body.max_topics)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/lessons/{lesson_id}/review/generate")
def generate_review(lesson_id: int, session: Session = Depends(get_session)):
    try:
        review, content = Planner(session).generate_review(lesson_id)
        return {"review_id": review.review_id, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reviews/{review_id}/evaluate", response_model=ReviewEvaluation)
def evaluate_review(
    review_id: int,
    body: EvaluateRequest,
    session: Session = Depends(get_session),
):
    try:
        return Planner(session).evaluate_review(review_id, body.submission)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/competencies/apply-delta")
def apply_delta(body: CompetencyDeltaRequest, session: Session = Depends(get_session)):
    Planner(session).apply_competency_delta(body.competency_id, body.delta)
    return {"applied": True, "competency_id": body.competency_id, "delta": body.delta}
