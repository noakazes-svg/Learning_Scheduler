# Learning Scheduler — Claude Working Notes

## Design Reference
All system design lives in [project_architecture/DESIGN.md](project_architecture/DESIGN.md).  
That file is the single source of truth for:
- System overview and objectives
- Component descriptions (Scraper, KB, Planner, Scheduler)
- Data model / ERD
- All process flows (Onboarding, Weekly Planning, Lesson Completion & Review)

**When a design decision changes, update DESIGN.md before or immediately after implementing it.**

## Project Structure
```
6_Learning_Scheduler/
├── project_architecture/
│   ├── DESIGN.md              ← authoritative design doc (read this first)
│   ├── Learning_Scheduler_v4.docx  ← original HLD (superseded by DESIGN.md)
│   └── maim flows/            ← original diagram images (superseded by DESIGN.md)
└── CLAUDE.md                  ← this file
```

## Working Process
- **Always write a plan first.** Before editing any file, describe what changes and in which files. Wait for explicit approval before writing code.

## Key Decisions
- KB is SQLite; lesson metadata in DB, lesson content in files.
- Scheduler supports Google Calendar only.
- Weekly cycle runs every Sunday at 07:00.
- Scheduler window: user-defined time blocks, Sun–Thu (Israeli work week).
  Blocks: Morning 09:00–12:30 · Afternoon 13:30–16:30 · Evening 17:00–20:00.
  Stored as JSON in Preferences.time_availability. Defaults to all blocks if unset.
- Competency scale: 1–5.
- LessonType: CompletedExperience | PlannedLesson | ManualLesson.
