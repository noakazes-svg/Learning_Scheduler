from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import get_all_events, get_events_for_week
from ...kb.database import get_session
from ...kb.models import CalendarEvent
from ...scheduler.scheduler import ScheduleResult, Scheduler, next_monday

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class ScheduleRequest(BaseModel):
    week_start: Optional[datetime] = None   # defaults to next Monday


@router.post("/schedule", response_model=ScheduleResult)
def build_schedule(body: ScheduleRequest, session: Session = Depends(get_session)):
    week_start = body.week_start or next_monday()
    try:
        return Scheduler(session).build_weekly_schedule(week_start)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/schedule", response_model=list[CalendarEvent])
def get_schedule(
    week_start: Optional[datetime] = None,
    session: Session = Depends(get_session),
):
    if week_start:
        return get_events_for_week(session, week_start)
    return get_all_events(session)
