from fastapi import FastAPI

from ..kb.database import init_db
from .routers import calendar, competencies, learning_paths, lessons, planner, reviews, scraper, scheduler, users

app = FastAPI(title="Learning Scheduler", version="0.1.0")

app.include_router(users.router)
app.include_router(competencies.router)
app.include_router(learning_paths.router)
app.include_router(lessons.router)
app.include_router(reviews.router)
app.include_router(calendar.router)
app.include_router(scraper.router)
app.include_router(planner.router)
app.include_router(scheduler.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
