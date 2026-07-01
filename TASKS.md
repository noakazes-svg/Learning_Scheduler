# Learning Scheduler — Task List

Legend: ✅ Done & tested · 🔄 Built (code written, not yet tested) · 📄 Docs/config only · ❌ Planned

| # | Area | Task | Status |
|---|------|------|--------|
| 1 | Data Model | Add `target_role` field to `User` model | 🔄 Built |
| 2 | Data Model | Add `Preferences` table (learning style, time availability, weekly hours, topics of interest) | 🔄 Built |
| 3 | Data Model | Add prerequisite relationships between learning paths | 🔄 Built |
| 4 | Onboarding | `POST /onboard` endpoint — full Flow 1 pipeline (profile → gaps → lessons → schedule) | ✅ Done |
| 5 | Onboarding | Self-assessment step — user rates current skill levels as part of onboarding | ✅ Done |
| 6 | Onboarding | Onboarding web form UI (HTML form) | ✅ Done |
| 7 | Planner | Prerequisite checking in planning cycle (verify prereqs before scheduling) | 🔄 Built |
| 8 | Planner | "No significant gaps" path — prompt user to choose more aspirational target role | 🔄 Built |
| 9 | Planner | Trigger replan after failed review (suggest remedial lessons, kick off new cycle) | 🔄 Built |
| 10 | Planner | Mid-week replanning — trigger replan when target role changes | 🔄 Built |
| 11 | Scheduler | Weekly automated trigger — runs every Sunday at 07:00 UTC | 🔄 Built |
| 12 | Scheduler | Respect user timezone in calendar events | 🔄 Built |
| 13 | Lesson Completion | `POST /lessons/{id}/complete` — marks done and auto-triggers review generation | 🔄 Built |
| 14 | Setup | Google Calendar credentials setup guide | 📄 Docs only |
| 15 | Setup | Startup validation — check all required env vars on app start | ✅ Done |
| 16 | Onboarding | Upload CV / certificate images — Claude vision extracts skills automatically | ✅ Done |
| 17 | Onboarding | Scheduling checkbox — clearer label + Sun–Thu description | ✅ Done |
| 18 | Scheduler | Work week changed to Sun–Thu (Israeli work days) | ✅ Done |
| 19 | Process | Plan-before-implement rule added to CLAUDE.md | 📄 Docs only |
| 20 | Scheduler | Fix Sunday trigger — schedule current week, not next week | ✅ Done |
| 21 | Scheduler | Mid-week replan triggers immediate rescheduling of current week | 🔄 Built |
| 22 | Preferences | Learning style: multi-select checkboxes (Visual/Reading/Hands-on/Video/Audio) | ✅ Done |
| 23 | Preferences | Time availability: Day × block grid (Sun–Thu × Morning/Afternoon/Evening) | ✅ Done |
| 24 | Scheduler | Scheduler respects user time blocks (09:00–12:30 / 13:30–16:30 / 17:00–20:00) | ✅ Done |
| 25 | Onboarding | Form saves answers to localStorage — restored automatically on reload | ✅ Done |
| 26 | Onboarding | Remove "Weekly Hours Available" field — redundant with time slots grid | ✅ Done |
| 27 | Setup | authorize_google.py — one-time Google Calendar OAuth from terminal | ✅ Done |
| 28 | Scheduler | Fix week start bug — was using Monday Jul 6 instead of Sunday Jul 5 | ✅ Done |
| 29 | Scheduler | Deduplicate lessons in DB — remove identical topic variants | ✅ Done |
| 30 | Scheduler | Round-robin lesson distribution — spreads lessons evenly across all 5 days | ✅ Done |
| 31 | Scraper | Fix `max_tokens` token limit causing `content` field to be missing in some lessons | ✅ Done |
| 32 | Planner | Fix prioritize call `max_tokens` (1024→4096) — was returning 0 topics for large gap lists | ✅ Done |
| 33 | Planner | Generate full lesson bank (30 topics) to fill all week slots + reserve | ✅ Done |
| 34 | Scheduler | Respect existing calendar events — freebusy check before booking | ✅ Done |
| 35 | Scraper | Lesson quality: task_type, action_steps, and direct resource links per lesson | ✅ Done |
| 36 | Scheduler | Calendar event display by type — color + emoji per task type (📖📗🎥💻🛠🎧) | ✅ Done |
| 37 | Scheduler | Fix timezone bug — blocks were in UTC (09:00 UTC = 12:00 Jerusalem); now uses user's local timezone | ✅ Done |
| 38 | Data Model | DB migration — added task_type column to lessons table | ✅ Done |
