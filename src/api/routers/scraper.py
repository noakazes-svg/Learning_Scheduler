from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...scraper.scraper import AssembledLesson, JobListing, Scraper

router = APIRouter(prefix="/scraper", tags=["scraper"])

_scraper = Scraper()


class LessonRequest(BaseModel):
    topic: str
    context: str = ""


class JobSearchRequest(BaseModel):
    role: str
    max_results: int = 5


@router.post("/lesson", response_model=AssembledLesson)
def assemble_lesson(body: LessonRequest):
    try:
        return _scraper.assemble_lesson(body.topic, body.context)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/jobs", response_model=list[JobListing])
def search_jobs(body: JobSearchRequest):
    return _scraper.search_job_listings(body.role, body.max_results)
