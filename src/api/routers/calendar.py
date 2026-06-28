from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ...kb.crud import (
    create_calendar_event,
    delete_events_for_week,
    get_all_events,
    get_events_for_week,
)
from ...kb.database import get_session
from ...kb.models import CalendarEvent

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEventCreate(BaseModel):
    lesson_id: int
    start_time: datetime
    end_time: datetime
    location_or_link: Optional[str] = None


@router.post("/events", response_model=CalendarEvent, status_code=201)
def create(body: CalendarEventCreate, session: Session = Depends(get_session)):
    return create_calendar_event(session, **body.model_dump())


@router.get("/events", response_model=list[CalendarEvent])
def list_all(session: Session = Depends(get_session)):
    return get_all_events(session)


@router.get("/events/week", response_model=list[CalendarEvent])
def list_for_week(week_start: datetime, session: Session = Depends(get_session)):
    return get_events_for_week(session, week_start)


@router.delete("/events/week")
def clear_week(week_start: datetime, session: Session = Depends(get_session)):
    count = delete_events_for_week(session, week_start)
    return {"deleted": count}
