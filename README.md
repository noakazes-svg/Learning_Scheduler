# Learning Scheduler

An intelligent, adaptive learning planning system that helps users close professional competency gaps through personalized learning plans.

## What It Does

The system maintains a knowledge profile of the user — competencies, learning history, projects, certifications, and career goals — and uses it to continuously generate and update learning paths aligned with a target role.

Every Sunday at 07:00 the system runs a weekly planning cycle: it identifies competency gaps, generates lessons (via web scraping + AI summaries), and schedules them into free calendar slots. After each lesson, the user takes a review (quiz, project, or exercise), and the results feed back into future planning.

## Architecture

Four components, one SQLite Knowledge Base:

| Component | Responsibility |
|-----------|---------------|
| **Knowledge Base** | SQLite DB + file store. Single source of truth for competencies, lessons, learning paths, reviews, and calendar events. |
| **Planner** | Reads gaps from the KB, determines learning paths, requests lesson generation, triggers reviews, updates competency estimates. Powered by Claude API. |
| **Scraper** | Searches the web for lesson material and job listings. Assembles lessons with AI-generated summaries. Powered by Tavily API + Claude API. |
| **Scheduler** | Allocates lessons into free Google Calendar slots (09:00–18:00). Rebuilds the schedule from scratch each week. |

## Tech Stack

- **Python** + **FastAPI** — REST API and onboarding web form
- **SQLModel** — ORM over SQLite
- **Anthropic Claude API** — Planner reasoning and lesson summarisation
- **Tavily API** — Web search for lessons and job listings
- **Google Calendar API** — Schedule publishing

## Project Structure

```
src/
├── kb/             # Knowledge Base: models, database, CRUD
├── planner/        # Gap analysis, path creation, review generation
├── scraper/        # Web search and lesson assembly
├── scheduler/      # Calendar slot allocation
└── api/
    ├── main.py
    └── routers/    # users, competencies, learning_paths, lessons, reviews, calendar
data/
└── lessons/        # Lesson content stored as markdown files
project_architecture/
└── DESIGN.md       # Full HLD: ERD + 3 process flow diagrams
```

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/noakazes-svg/Learning_Scheduler.git
   cd Learning_Scheduler
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Fill in your API keys in .env
   ```

5. **Run the API**
   ```bash
   uvicorn src.api.main:app --reload
   ```
   API docs available at `http://localhost:8000/docs`

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/users/` | Create user profile |
| GET | `/users/me` | Get current user |
| GET/PUT | `/competencies/` | Manage competencies |
| GET | `/competencies/gaps` | List skills where current < target level |
| GET/POST | `/learning-paths/` | Manage learning paths |
| GET/POST | `/lessons/` | Manage lessons |
| GET/PUT | `/lessons/{id}/content` | Read/write lesson content file |
| PATCH | `/lessons/{id}/status` | Mark lesson in progress / completed |
| POST | `/reviews/` | Create a review for a lesson |
| POST | `/reviews/{id}/results` | Submit review result |
| GET | `/calendar/events/week` | Get scheduled events for a week |
| DELETE | `/calendar/events/week` | Clear a week's schedule (for rebuild) |

## Process Flows

See [`project_architecture/DESIGN.md`](project_architecture/DESIGN.md) for full Mermaid diagrams of all three flows:

1. **Onboarding & Update Flow** — ingest profile, assess gaps, generate lessons, schedule
2. **Weekly Planning Flow** — runs every Sunday 07:00, rebuilds next week's schedule
3. **Lesson Completion & Review Flow** — evaluate learning, update competency, adapt future plans
