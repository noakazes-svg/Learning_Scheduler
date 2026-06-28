# Learning Scheduler — Task List

All 15 tasks required to complete the planned system. No scope changes until all are done.

| # | Area | Task | Status |
|---|------|------|--------|
| 1 | Data Model | Add `target_role` field to `User` model | ✅ Done |
| 2 | Data Model | Add `Preferences` table (learning style, time availability, weekly hours, topics of interest) | ✅ Done |
| 3 | Data Model | Add prerequisite relationships between learning paths | ✅ Done |
| 4 | Onboarding | `POST /onboard` endpoint — full Flow 1 pipeline (profile → gaps → lessons → schedule) | ✅ Done |
| 5 | Onboarding | Self-assessment step — user rates current skill levels as part of onboarding | ✅ Done |
| 6 | Onboarding | Onboarding web form UI (HTML form) | ✅ Done |
| 7 | Planner | Prerequisite checking in planning cycle (verify prereqs before scheduling) | ✅ Done |
| 8 | Planner | "No significant gaps" path — prompt user to choose more aspirational target role | ✅ Done |
| 9 | Planner | Trigger replan after failed review (suggest remedial lessons, kick off new cycle) | ✅ Done |
| 10 | Planner | Mid-week replanning — trigger replan when target role changes | ✅ Done |
| 11 | Scheduler | Weekly automated trigger — cron job every Sunday at 07:00 UTC | ✅ Done |
| 12 | Scheduler | Respect user timezone in calendar events (currently hardcoded UTC) | ✅ Done |
| 13 | Lesson Completion | `POST /lessons/{id}/complete` — marks done and auto-triggers review generation | ✅ Done |
| 14 | Setup | Google Calendar credentials setup guide | ✅ Done |
| 15 | Setup | Startup validation — check all required env vars on app start | ✅ Done |
