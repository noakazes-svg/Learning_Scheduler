from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from sqlmodel import Session, select

from .models import (
    CalendarEvent,
    Competency,
    Lesson,
    LearningPath,
    Review,
    ReviewResult,
    User,
)

_LESSON_CONTENT_DIR = Path(__file__).parent.parent.parent / "data" / "lessons"
_LESSON_CONTENT_DIR.mkdir(parents=True, exist_ok=True)

_REVIEW_CONTENT_DIR = Path(__file__).parent.parent.parent / "data" / "reviews"
_REVIEW_CONTENT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def create_user(session: Session, first_name: str, last_name: str, email: str, timezone: str) -> User:
    user = User(first_name=first_name, last_name=last_name, email=email, timezone=timezone)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user(session: Session) -> Optional[User]:
    return session.exec(select(User)).first()


def update_user(session: Session, user_id: int, **fields) -> Optional[User]:
    user = session.get(User, user_id)
    if not user:
        return None
    for key, value in fields.items():
        setattr(user, key, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# LearningPath
# ---------------------------------------------------------------------------

def create_learning_path(session: Session, user_id: int, title: str, status: str = "Active") -> LearningPath:
    path = LearningPath(user_id=user_id, title=title, status=status)
    session.add(path)
    session.commit()
    session.refresh(path)
    return path


def get_learning_paths(session: Session, user_id: int) -> list[LearningPath]:
    return list(session.exec(select(LearningPath).where(LearningPath.user_id == user_id)))


def update_learning_path(session: Session, learning_path_id: int, **fields) -> Optional[LearningPath]:
    path = session.get(LearningPath, learning_path_id)
    if not path:
        return None
    for key, value in fields.items():
        setattr(path, key, value)
    session.add(path)
    session.commit()
    session.refresh(path)
    return path


# ---------------------------------------------------------------------------
# Lesson
# ---------------------------------------------------------------------------

def create_lesson(
    session: Session,
    topic: str,
    lesson_type: str,
    learning_path_id: Optional[int] = None,
    content: Optional[str] = None,
    **fields,
) -> Lesson:
    lesson = Lesson(topic=topic, lesson_type=lesson_type, learning_path_id=learning_path_id, **fields)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    if content:
        save_lesson_content(lesson.lesson_id, content)
    return lesson


def get_lesson(session: Session, lesson_id: int) -> Optional[Lesson]:
    return session.get(Lesson, lesson_id)


def get_lessons(
    session: Session,
    learning_path_id: Optional[int] = None,
    status: Optional[str] = None,
    lesson_type: Optional[str] = None,
) -> list[Lesson]:
    stmt = select(Lesson)
    if learning_path_id is not None:
        stmt = stmt.where(Lesson.learning_path_id == learning_path_id)
    if status:
        stmt = stmt.where(Lesson.status == status)
    if lesson_type:
        stmt = stmt.where(Lesson.lesson_type == lesson_type)
    return list(session.exec(stmt))


def get_planned_lessons(session: Session) -> list[Lesson]:
    return get_lessons(session, status="Planned")


def update_lesson_status(
    session: Session,
    lesson_id: int,
    status: str,
    completed_date: Optional[date] = None,
) -> Optional[Lesson]:
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        return None
    lesson.status = status
    if completed_date:
        lesson.completed_date = completed_date
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def update_lesson(session: Session, lesson_id: int, **fields) -> Optional[Lesson]:
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        return None
    for key, value in fields.items():
        setattr(lesson, key, value)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


# Lesson content stored as markdown files on disk
def save_lesson_content(lesson_id: int, content: str) -> None:
    (_LESSON_CONTENT_DIR / f"{lesson_id}.md").write_text(content, encoding="utf-8")


def load_lesson_content(lesson_id: int) -> Optional[str]:
    path = _LESSON_CONTENT_DIR / f"{lesson_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


# ---------------------------------------------------------------------------
# Competency
# ---------------------------------------------------------------------------

def create_competency(
    session: Session,
    user_id: int,
    skill_name: str,
    current_level: int,
    target_level: int,
    description: Optional[str] = None,
    priority: Optional[str] = None,
) -> Competency:
    comp = Competency(
        user_id=user_id,
        skill_name=skill_name,
        current_level=current_level,
        target_level=target_level,
        description=description,
        priority=priority,
    )
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


def get_competencies(session: Session, user_id: int) -> list[Competency]:
    return list(session.exec(select(Competency).where(Competency.user_id == user_id)))


def get_competency_gaps(session: Session, user_id: int) -> list[Competency]:
    """Return competencies where current_level < target_level, ordered by priority."""
    stmt = (
        select(Competency)
        .where(Competency.user_id == user_id)
        .where(Competency.current_level < Competency.target_level)
    )
    return list(session.exec(stmt))


def update_competency_level(
    session: Session,
    competency_id: int,
    current_level: int,
) -> Optional[Competency]:
    comp = session.get(Competency, competency_id)
    if not comp:
        return None
    comp.current_level = current_level
    comp.last_updated = datetime.utcnow()
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


def upsert_competency(
    session: Session,
    user_id: int,
    skill_name: str,
    current_level: int,
    target_level: int,
    **fields,
) -> Competency:
    existing = session.exec(
        select(Competency)
        .where(Competency.user_id == user_id)
        .where(Competency.skill_name == skill_name)
    ).first()
    if existing:
        existing.current_level = current_level
        existing.target_level = target_level
        existing.last_updated = datetime.utcnow()
        for key, value in fields.items():
            setattr(existing, key, value)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    return create_competency(session, user_id, skill_name, current_level, target_level, **fields)


# Review content stored as JSON files on disk (questions, exercises, instructions)
def save_review_content(review_id: int, content: dict) -> None:
    import json
    (_REVIEW_CONTENT_DIR / f"{review_id}.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_review_content(review_id: int) -> Optional[dict]:
    import json
    path = _REVIEW_CONTENT_DIR / f"{review_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

def create_review(
    session: Session,
    lesson_id: int,
    review_type: str,
    due_date: Optional[date] = None,
) -> Review:
    review = Review(lesson_id=lesson_id, review_type=review_type, due_date=due_date)
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


def get_reviews(session: Session, lesson_id: int) -> list[Review]:
    return list(session.exec(select(Review).where(Review.lesson_id == lesson_id)))


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------

def create_review_result(
    session: Session,
    review_id: int,
    score: Optional[float] = None,
    max_score: Optional[float] = None,
    passed: Optional[bool] = None,
    feedback: Optional[str] = None,
) -> ReviewResult:
    result = ReviewResult(
        review_id=review_id,
        score=score,
        max_score=max_score,
        passed=passed,
        completed_date=date.today(),
        feedback=feedback,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


def get_review_results(session: Session, review_id: int) -> list[ReviewResult]:
    return list(session.exec(select(ReviewResult).where(ReviewResult.review_id == review_id)))


# ---------------------------------------------------------------------------
# CalendarEvent
# ---------------------------------------------------------------------------

def create_calendar_event(
    session: Session,
    lesson_id: int,
    start_time: datetime,
    end_time: datetime,
    location_or_link: Optional[str] = None,
) -> CalendarEvent:
    event = CalendarEvent(
        lesson_id=lesson_id,
        start_time=start_time,
        end_time=end_time,
        location_or_link=location_or_link,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def get_events_for_week(session: Session, week_start: datetime) -> list[CalendarEvent]:
    week_end = week_start + timedelta(days=7) - timedelta(seconds=1)
    return list(
        session.exec(
            select(CalendarEvent)
            .where(CalendarEvent.start_time >= week_start)
            .where(CalendarEvent.start_time <= week_end)
        )
    )


def delete_events_for_week(session: Session, week_start: datetime) -> int:
    events = get_events_for_week(session, week_start)
    for event in events:
        session.delete(event)
    session.commit()
    return len(events)


def get_all_events(session: Session) -> list[CalendarEvent]:
    return list(session.exec(select(CalendarEvent)))
