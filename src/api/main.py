import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from ..kb.database import get_session, init_db
from ..planner.planner import Planner
from ..scheduler.scheduler import Scheduler, next_monday
from .routers import (
    calendar,
    competencies,
    learning_paths,
    lessons,
    onboarding,
    planner,
    reviews,
    scraper,
    scheduler,
    users,
)

_REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "GOOGLE_CALENDAR_CREDENTIALS_FILE",
]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Weekly background trigger — runs every Sunday at 07:00 UTC
# ---------------------------------------------------------------------------

def _seconds_until_next_sunday_0700() -> float:
    now = datetime.now(timezone.utc)
    days_until_sunday = (6 - now.weekday()) % 7  # weekday(): Monday=0, Sunday=6
    next_sunday = (now + timedelta(days=days_until_sunday)).replace(
        hour=7, minute=0, second=0, microsecond=0
    )
    if next_sunday <= now:
        next_sunday += timedelta(weeks=1)
    return (next_sunday - now).total_seconds()


async def _weekly_planner_loop() -> None:
    while True:
        wait = _seconds_until_next_sunday_0700()
        log.info("Weekly planner: sleeping %.0f s until next Sunday 07:00 UTC", wait)
        await asyncio.sleep(wait)
        try:
            session_gen = get_session()
            session = next(session_gen)
            try:
                log.info("Weekly planner: running planning cycle")
                result = Planner(session).run_planning_cycle()
                if result.no_gaps:
                    log.info("Weekly planner: no competency gaps — skipping scheduling")
                elif result.lessons_created:
                    log.info("Weekly planner: generated %d lessons — scheduling", len(result.lessons_created))
                    Scheduler(session).build_weekly_schedule(next_monday())
                else:
                    log.info("Weekly planner: no lessons generated (all topics skipped)")
            finally:
                try:
                    next(session_gen)
                except StopIteration:
                    pass
        except Exception:
            log.exception("Weekly planner: error during cycle — will retry next Sunday")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_env()
    init_db()
    task = asyncio.create_task(_weekly_planner_loop())
    log.info("Weekly planner task started")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Learning Scheduler", version="0.1.0", lifespan=lifespan)

app.include_router(users.router)
app.include_router(competencies.router)
app.include_router(learning_paths.router)
app.include_router(lessons.router)
app.include_router(reviews.router)
app.include_router(calendar.router)
app.include_router(scraper.router)
app.include_router(planner.router)
app.include_router(scheduler.router)
app.include_router(onboarding.router)


def _validate_env() -> None:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in your API keys."
        )


@app.get("/health")
def health():
    return {"status": "ok"}
