import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import BaseModel
from sqlmodel import Session

from ..kb import crud
from ..kb.models import Lesson

SCOPES = ["https://www.googleapis.com/auth/calendar"]
BUFFER_MINUTES = 15    # gap between consecutive lessons

# User-selectable time blocks (start_hour, start_min, end_hour, end_min)
TIME_BLOCKS = {
    "morning":   (9,  0,  12, 30),
    "afternoon": (13, 30, 16, 30),
    "evening":   (17, 0,  20, 0),
}
DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu"]


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class TimeSlot(BaseModel):
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)


class ScheduleResult(BaseModel):
    week_start: str
    lessons_scheduled: int
    lessons_skipped: int
    event_ids: list[int]   # KB CalendarEvent IDs


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    def __init__(self, session: Session):
        self.session = session
        self._service = None   # lazy — only built on first use

    @property
    def service(self):
        if self._service is None:
            self._service = _build_calendar_service()
        return self._service

    def build_weekly_schedule(self, week_start: datetime) -> ScheduleResult:
        """Clear the week's existing schedule and rebuild it from planned lessons."""
        user = crud.get_user(self.session)
        self._timezone = (user.timezone if user else "UTC")

        # 1. Wipe existing KB events for this week
        crud.delete_events_for_week(self.session, week_start)

        # 2. Load planned lessons ordered by priority
        lessons = self._get_prioritized_lessons()
        if not lessons:
            return ScheduleResult(
                week_start=week_start.isoformat(),
                lessons_scheduled=0,
                lessons_skipped=0,
                event_ids=[],
            )

        # 3. Get free slots from Google Calendar
        free_slots = self._get_free_slots(week_start)

        # 4. Allocate each lesson to the earliest fitting slot
        event_ids: list[int] = []
        skipped = 0

        for lesson in lessons:
            duration = lesson.duration_minutes or 60
            slot = _find_slot(free_slots, duration)
            if not slot:
                skipped += 1
                continue

            lesson_end = slot.start + timedelta(minutes=duration)

            # Write to Google Calendar
            gc_event_id = self._create_google_event(lesson, slot.start, lesson_end)

            # Persist in KB
            event = crud.create_calendar_event(
                self.session,
                lesson_id=lesson.lesson_id,
                start_time=slot.start,
                end_time=lesson_end,
                location_or_link=gc_event_id,
            )
            event_ids.append(event.event_id)

            # Remove used time (+ buffer) from free slots
            free_slots = _consume_slot(
                free_slots,
                used_start=slot.start,
                used_end=lesson_end + timedelta(minutes=BUFFER_MINUTES),
            )

        return ScheduleResult(
            week_start=week_start.isoformat(),
            lessons_scheduled=len(event_ids),
            lessons_skipped=skipped,
            event_ids=event_ids,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_prioritized_lessons(self) -> list[Lesson]:
        """Return planned lessons, shortest-first as a scheduling heuristic."""
        lessons = crud.get_planned_lessons(self.session)
        return sorted(lessons, key=lambda l: l.duration_minutes or 60)

    def _get_free_slots(self, week_start: datetime) -> list[TimeSlot]:
        """Query Google Calendar freebusy and return free windows within the user's time blocks."""
        week_end = week_start + timedelta(days=5)   # Sun–Thu only

        result = self.service.freebusy().query(body={
            "timeMin": _to_rfc3339(week_start),
            "timeMax": _to_rfc3339(week_end),
            "items": [{"id": "primary"}],
        }).execute()

        busy_raw = result.get("calendars", {}).get("primary", {}).get("busy", [])
        busy = [
            (_parse_dt(b["start"]), _parse_dt(b["end"]))
            for b in busy_raw
        ]

        # Load user time-block preferences
        user = crud.get_user(self.session)
        availability: dict = {}
        if user:
            prefs = crud.get_preferences(self.session, user.user_id)
            if prefs and prefs.time_availability:
                try:
                    availability = json.loads(prefs.time_availability)
                except (json.JSONDecodeError, TypeError):
                    pass

        free_slots: list[TimeSlot] = []

        for day_offset in range(5):   # Sun–Thu
            day = week_start + timedelta(days=day_offset)
            day_name = DAY_NAMES[day_offset]

            # Default: all blocks if user hasn't set preferences
            selected = availability.get(day_name, list(TIME_BLOCKS.keys()))

            for block_name in ("morning", "afternoon", "evening"):
                if block_name not in selected:
                    continue
                sh, sm, eh, em = TIME_BLOCKS[block_name]
                block_start = day.replace(hour=sh, minute=sm, second=0, microsecond=0)
                block_end   = day.replace(hour=eh, minute=em, second=0, microsecond=0)

                # Busy periods overlapping this block
                block_busy = sorted(
                    (max(s, block_start), min(e, block_end))
                    for s, e in busy
                    if s < block_end and e > block_start
                )

                current = block_start
                for busy_start, busy_end in block_busy:
                    if busy_start > current:
                        free_slots.append(TimeSlot(start=current, end=busy_start))
                    current = max(current, busy_end)

                if current < block_end:
                    free_slots.append(TimeSlot(start=current, end=block_end))

        return free_slots

    def _create_google_event(self, lesson: Lesson, start: datetime, end: datetime) -> str:
        """Create a Google Calendar event and return its event ID."""
        tz = getattr(self, "_timezone", "UTC")
        event_body = {
            "summary": f"Learn: {lesson.topic}",
            "description": (
                f"Category: {lesson.category or 'General'}\n"
                f"Difficulty: {lesson.difficulty or 'N/A'}\n\n"
                f"Objectives:\n{lesson.objectives or ''}"
            ),
            "start": {"dateTime": _to_rfc3339(start), "timeZone": tz},
            "end": {"dateTime": _to_rfc3339(end), "timeZone": tz},
            "colorId": "7",  # Peacock blue
        }
        created = self.service.events().insert(calendarId="primary", body=event_body).execute()
        return created.get("id", "")


# ---------------------------------------------------------------------------
# Slot helpers
# ---------------------------------------------------------------------------

def _find_slot(slots: list[TimeSlot], duration_minutes: int) -> Optional[TimeSlot]:
    return next((s for s in slots if s.duration_minutes >= duration_minutes), None)


def _consume_slot(
    slots: list[TimeSlot], used_start: datetime, used_end: datetime
) -> list[TimeSlot]:
    """Subtract a used time window from the free slot list."""
    result: list[TimeSlot] = []
    for slot in slots:
        if slot.end <= used_start or slot.start >= used_end:
            result.append(slot)
        else:
            if slot.start < used_start:
                result.append(TimeSlot(start=slot.start, end=used_start))
            if slot.end > used_end:
                result.append(TimeSlot(start=used_end, end=slot.end))
    return result


# ---------------------------------------------------------------------------
# Google Calendar auth
# ---------------------------------------------------------------------------

def _build_calendar_service():
    """Authenticate and return an authorized Google Calendar API client."""
    token_path = "token.json"
    creds_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "credentials.json")
    creds: Optional[Credentials] = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Google Calendar credentials not found at '{creds_path}'. "
                    "Download OAuth2 credentials from Google Cloud Console and set "
                    "GOOGLE_CALENDAR_CREDENTIALS_FILE in your .env file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Datetime utilities
# ---------------------------------------------------------------------------

def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Return as naive UTC for uniform comparison
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def next_sunday(from_dt: Optional[datetime] = None) -> datetime:
    """Return the next (future) Sunday at 00:00 UTC — used by onboarding."""
    base = from_dt or datetime.utcnow()
    days_ahead = (6 - base.weekday()) % 7 or 7
    return (base + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def current_week_sunday(from_dt: Optional[datetime] = None) -> datetime:
    """Return the most recent Sunday at 00:00 UTC — the start of the current work week."""
    base = from_dt or datetime.utcnow()
    # weekday(): Mon=0 … Sun=6  →  days since last Sunday = (weekday + 1) % 7
    days_since_sunday = (base.weekday() + 1) % 7
    return (base - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


# Keep old name as alias so existing imports don't break
next_monday = next_sunday
