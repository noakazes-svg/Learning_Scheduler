from datetime import date, datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str
    last_name: str
    email: str = Field(unique=True)
    timezone: str
    target_role: Optional[str] = None   # Task 1: e.g. "Data Analyst", "ML Engineer"
    created_date: datetime = Field(default_factory=datetime.utcnow)


class Preferences(SQLModel, table=True):
    __tablename__ = "preferences"

    preferences_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", unique=True)
    learning_style: Optional[str] = None       # e.g. Visual | Reading | Hands-on
    weekly_hours: Optional[int] = None         # hours available per week
    time_availability: Optional[str] = None    # e.g. "Mornings", "Evenings", "Flexible"
    topics_of_interest: Optional[str] = None   # comma-separated


class LearningPath(SQLModel, table=True):
    __tablename__ = "learning_paths"

    learning_path_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id")
    title: str
    status: str = "Active"
    created_date: datetime = Field(default_factory=datetime.utcnow)


class LearningPathPrerequisite(SQLModel, table=True):
    __tablename__ = "learning_path_prerequisites"

    id: Optional[int] = Field(default=None, primary_key=True)
    learning_path_id: int = Field(foreign_key="learning_paths.learning_path_id")
    prerequisite_path_id: int = Field(foreign_key="learning_paths.learning_path_id")


class Lesson(SQLModel, table=True):
    __tablename__ = "lessons"

    lesson_id: Optional[int] = Field(default=None, primary_key=True)
    learning_path_id: Optional[int] = Field(default=None, foreign_key="learning_paths.learning_path_id")
    topic: str
    category: Optional[str] = None
    difficulty: Optional[str] = None
    duration_minutes: Optional[int] = None
    objectives: Optional[str] = None
    # source / evidence fields (used when LessonType = CompletedExperience)
    source: Optional[str] = None
    evidence_type: Optional[str] = None
    evidence_date: Optional[date] = None
    # lifecycle
    status: str = "Planned"            # Planned | In Progress | Completed | Archived
    lesson_type: str = "PlannedLesson" # CompletedExperience | PlannedLesson | ManualLesson
    completed_date: Optional[date] = None
    created_date: datetime = Field(default_factory=datetime.utcnow)


class Review(SQLModel, table=True):
    __tablename__ = "reviews"

    review_id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lessons.lesson_id")
    review_type: str       # Quiz | Project | Exercise | Assessment
    created_date: datetime = Field(default_factory=datetime.utcnow)
    due_date: Optional[date] = None


class ReviewResult(SQLModel, table=True):
    __tablename__ = "review_results"

    result_id: Optional[int] = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="reviews.review_id")
    score: Optional[float] = None
    max_score: Optional[float] = None
    passed: Optional[bool] = None
    completed_date: Optional[date] = None
    feedback: Optional[str] = None


class Competency(SQLModel, table=True):
    __tablename__ = "competencies"

    competency_id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id")
    skill_name: str
    description: Optional[str] = None
    current_level: int = Field(ge=1, le=5)   # 1–5
    target_level: int = Field(ge=1, le=5)    # 1–5
    priority: Optional[str] = None           # High | Medium | Low
    status: str = "Active"
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class CalendarEvent(SQLModel, table=True):
    __tablename__ = "calendar_events"

    event_id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lessons.lesson_id")
    start_time: datetime
    end_time: datetime
    location_or_link: Optional[str] = None
    status: str = "Planned"
    created_date: datetime = Field(default_factory=datetime.utcnow)
