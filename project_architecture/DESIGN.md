# Learning Scheduler — High Level Design

## System Overview

### System Description

The Learning Scheduler is an intelligent learning-planning system designed to help users close professional competency gaps through personalized, adaptive learning plans.

The system maintains a knowledge profile of the user, including their current competencies, learning history, completed lessons, projects, certifications, career goals, and identified skill gaps. Based on this information, the system continuously generates and updates learning paths that are aligned with the user's target role and professional objectives.

The system operates through a weekly planning cycle that analyzes the user's current state, identifies competency gaps, prioritizes learning topics, generates lessons, and schedules learning activities into available calendar slots. The planning cycle runs automatically every Sunday at 07:00 and creates a learning schedule for the upcoming week.

Users may also update the system manually by submitting new information such as completed courses, projects, certifications, competency updates, or changes to career goals. Significant updates trigger a re-evaluation of competencies, learning paths, and scheduling decisions.

The system uses a feedback-driven learning model. After completing lessons, users perform reviews that may include quizzes, projects, exercises, or assessments. Review results are used to update competency estimates and recalculate future learning priorities. This feedback loop enables the system to continuously adapt learning plans based on demonstrated progress.

The system is composed of four primary components:

- **Knowledge Base (KB)** — stores competencies, learning history, lessons, reviews, learning paths, evidence, and career objectives.
- **Planner** — analyzes competency gaps, prioritizes learning objectives, creates learning paths, and generates reviews.
- **Scraper** — gathers external learning resources and assembles lessons using publicly available content and AI-generated summaries.
- **Scheduler** — allocates learning activities into available calendar slots and maintains the weekly learning schedule.

The Knowledge Base serves as the system of record, while the review process serves as the primary feedback mechanism that continuously improves competency estimates and drives future planning decisions.

The overall objective of the system is to provide a personalized, adaptive, and continuously evolving learning experience that helps users efficiently progress toward their target professional roles.

---

## Primary Processes

## Components

### Scraper

**High-Level Description:** The component is responsible for obtaining web data in order to support the requirements of the different components. The component receives requests to look up specific, defined types of web data, performs searches to obtain that data, and returns it to the requester.

**Main Process Flows:**
- Obtaining public job listings — the component receives requests to obtain public job listings for a specified role/title and searches for job descriptions matching that role/title and returns the contents and metadata of all applicable job postings.
- Looking up lesson material / available training related to a specific subject — the component receives requests to obtain material used to learn about a specific subject and returns it.
- Assemble lessons based on requested topics.
- Build lesson content using external learning resources and AI-generated summaries.
- Generate lesson metadata, exercises and review material.
- Return completed lessons to the planner.

**Component Dependencies:** None — component is independent, searching publicly accessible internet pages.

**Data Dependencies:** Job Listings, Lessons.

### Knowledge Base (KB)

**High-Level Description:** The component is responsible for holding data about what the user knows, their competency, and what their gaps are. Additionally, the KB holds the contents of lessons, both the ones already completed by the user and ones that aren't. The component receives requests to update the list of topics according to user updates or updates from the scraper.

The KB will be based on a SQLite database. KB will store lesson metadata in the DB and lesson contents in files.

**Main Process Flows:**
- Holds data related to the knowledge of the user, their competency, and what their gaps are. The component receives requests to update the list of topics according to user updates or updates from the scraper.
- Holds contents of lessons and their associated metadata. The component receives requests to add lessons from the scraper.
- Receives requests to update completion of user lessons from the planner, and update user competency of topics.
- Store competency evidence.
- Store learning paths.
- Store review results.
- Receive onboarding information from CV, LinkedIn, projects, self-assessment and job target.

**Component Dependencies:** None — component is independent.

**Data Dependencies:** Lessons, Topic Competency, Learning Paths, Competency Evidence, Review Results.

### Planner

**High-Level Description:** The component is responsible for getting data about the user competency gaps from the KB. According to the data that the component receives from the KB, the planner needs to send requests to the scraper to create lessons based on the topics that the user needs to work on.

**Main Process Flows:**
- Getting data about the user competency gaps from the KB.
- The planner sends requests to the scraper to create lessons.
- After completion of lessons, the planner updates the KB on lessons status and topic competency.
- Determine required learning paths based on competency gaps.
- Request lesson generation for the required topics from the scraper.
- Trigger review generation after lesson completion.
- Update competency according to quiz and project review results.
- Store generated lessons in the KB.
- Generate reviews.

**Component Dependencies:** Knowledge Base, Scraper.

**Data Dependencies:** Topic Competency, Lessons.

### Scheduler

**High-Level Description:** The component is responsible for getting data about the lessons needed to be scheduled — their topics, their length, etc. According to the data the component receives from the planner, the scheduler needs to update the user's calendar.

The scheduler will only support Google Calendar for scheduling.

**Main Process Flows:**
- Getting data about the lessons needed to be scheduled.
- The scheduler needs to update the user calendar.
- The scheduler operates as part of a weekly planning cycle.
- The schedule is recreated from scratch once per week.
- The scheduler identifies free calendar slots between 09:00 and 18:00.
- Manual KB updates can trigger schedule regeneration.
- Only the next week is planned.
- If there is insufficient time, prioritize highest-priority lessons.

**Component Dependencies:** Planner.

**Data Dependencies:** Lessons.

---

## Data Model (ERD)

```mermaid
erDiagram
    USER {
        int UserID PK
        string FirstName
        string LastName
        string Email
        string Timezone
        date CreatedDate
    }
    LEARNINGPATH {
        int LearningPathID PK
        string Title
        string Status
        date CreatedDate
    }
    LESSON {
        int LessonID PK
        int LearningPathID FK
        string Topic
        string Category
        string Difficulty
        int DurationMinutes
        text Objectives
        string Source
        string EvidenceType
        date EvidenceDate
        string Status
        string LessonType
        date CompletedDate
        date CreatedDate
    }
    REVIEW {
        int ReviewID PK
        int LessonID FK
        string ReviewType
        date CreatedDate
        date DueDate
    }
    REVIEWRESULT {
        int ResultID PK
        int ReviewID FK
        float Score
        float MaxScore
        bool Passed
        date CompletedDate
        text Feedback
    }
    COMPETENCY {
        int CompetencyID PK
        int UserID FK
        string SkillName
        text Description
        int CurrentLevel
        int TargetLevel
        string Priority
        string Status
        date LastUpdated
    }
    CALENDAREVENT {
        int EventID PK
        int LessonID FK
        datetime StartTime
        datetime EndTime
        string LocationOrLink
        string Status
        date CreatedDate
    }

    USER ||--o{ LEARNINGPATH : "has"
    LEARNINGPATH ||--|{ LESSON : "contains"
    LESSON ||--o{ REVIEW : "triggers"
    REVIEW ||--o{ REVIEWRESULT : "produces"
    USER ||--o{ COMPETENCY : "has"
    LESSON ||--o{ CALENDAREVENT : "scheduled as"
```

**LessonType values:**
- `CompletedExperience` — already completed by the user (e.g., job experience, course, project, certification)
- `PlannedLesson` — generated by the Planner to fill a competency gap
- `ManualLesson` — added manually by the user

**Notes:**
- There is a single User in the system.
- All knowledge (past experience or future learning) is stored as a Lesson.
- Evidence is represented as Lessons with `LessonType = CompletedExperience`.
- Competency is simplified to a single entity with 1–5 level ranking.
- Lesson Status examples: Planned, In Progress, Completed, Archived.
- CurrentLevel and TargetLevel range: 1–5.

---

## Flow 1: Onboarding & Update Flow

**Goal:** Continuously assess gaps, schedule learning, and adapt as the user grows. Allow user to manually update information and keep the system accurate and up to date.

**Inputs (Web Form):**
- Personal & Background (CV): name, role, location, summary
- Skills & Experience: skills, tools, years of experience, achievements
- Past Projects: project name, description, role, impact, tech used
- Target Role / Goal: desired role, level, key responsibilities, must-have skills
- Courses / Certifications: name, provider, date, status, score
- Preferences: learning style, time availability, weekly hours, topics of interest

```mermaid
flowchart TD
    Start([Start]) --> S1[1. Ingest / Update Profile\nFrom Web Form]
    S1 --> S2[2. Self Assessment\nRate current skills]
    S2 --> S3[3. Select / Confirm Target Role\ne.g. Data Analyst]
    S3 --> S4[4. Initialize Knowledge Base\nCompetencies & Evidence]
    S4 --> S5[5. Gap Analysis\nPlanner]
    S5 --> D6{6. Are there\nSignificant Gaps?}
    D6 -- No --> S6A[6A. No Significant Gaps\nChoose a More Aspirational Role / Goal]
    S6A --> S3
    D6 -- Yes --> S7[7. Create Learning Paths\nPlanner]
    S7 --> S8[8. Request Lesson Generation\nfor Each Topic - Scraper]
    S8 --> S9[9. Scraper Searches & Builds Lessons\nExternal Content + AI Summary]
    S9 --> S10[10. Lessons Stored in KB]
    S10 --> S11[11. Schedule This Week\nScheduler]
    S11 --> D12{12. Any Conflicts\nor Not Enough Time?}
    D12 -- Yes --> S12A[Resolve Conflicts /\nAdjust Lessons]
    S12A --> S11
    D12 -- No --> S13[13. Publish Current Week Plan\nto Calendar]
    S13 --> End([Onboarding / Update Complete])
```

**Notes:**
- The system assumes lessons are completed successfully when planning the week.
- Replanning is triggered by significant changes only.
- All updates (profile or progress) flow through the same process.
- The Knowledge Base (KB) is the single source of truth.

---

## Flow 2: Weekly Planning Flow

**Goal:** Review current state, find gaps, plan learning, generate lessons, and schedule the next week.

**Trigger:** Every Sunday at 07:00.

```mermaid
flowchart TD
    Trigger([07:00 Sunday Morning\nWeekly Trigger]) --> S1[1. Planner Reads Data from KB\nCompetencies, Progress, Reviews,\nLearning Paths, Calendar]
    S1 --> S2[2. Identify Knowledge Gaps\nCompare Target vs Current]
    S2 --> D3{3. Any Significant\nGaps?}
    D3 -- No --> NoGaps[No Major Gaps Found]
    NoGaps --> User([USER: Select a new\ntarget role — flow restarts])
    User -.->|New target selected| S1
    D3 -- Yes --> S4[4. Prioritize Gaps\nImpact, Urgency, Dependencies]
    S4 --> S5[5. Create / Update Learning Paths\nPlanner]
    S5 --> S6[6. Check Prerequisites\nfor Each Path]
    S6 --> D7{7. Are All Prerequisites\nCompleted?}
    D7 -- No --> S7A[Schedule Prerequisite\nLessons First - Add to Plan]
    S7A --> S6
    D7 -- Yes --> S8[8. Request Lesson Generation\nfor Each Topic - Planner]
    S8 --> S9[9. Scraper Searches & Builds Lessons\nExternal Content + AI Summary]
    S9 --> D10{10. Enough Quality\nLessons Found?}
    D10 -- No --> S10A[Refine Search / Adjust\nTopic Scope / Flag for Manual Review]
    S10A --> S9
    D10 -- Yes --> S11[11. Lessons Stored / Updated in KB]
    S11 --> S12[12. Estimate Learning Time\nfor Each Lesson]
    S12 --> S13[13. Get Free Calendar Slots\n09:00 - 18:00]
    S13 --> D14{14. Enough Time\nAvailable?}
    D14 -- No --> S14A[Reduce Scope / Lower Priority /\nSpread to Future Weeks]
    S14A --> S15[15. Build Weekly Schedule\nScheduler]
    D14 -- Yes --> S15
    S15 --> D16{16. Any Conflicts?}
    D16 -- Yes --> S16A[Resolve Conflicts /\nAdjust Lessons]
    S16A --> S15
    D16 -- No --> S17[17. Update Calendar with\nNew Weekly Plan]
    S17 --> End([Weekly Plan Published\nNext Week Ready])
    End -.->|Next Sunday 07:00| Trigger
```

**About loop directions:**
- **Rightward "No" arrows** (steps 7 and 10): Perform an action to fix the issue, then continue forward to re-check.
- **Leftward "No" arrows** (steps 14 and 16): Adjust the plan (reduce scope or resolve conflicts), then return to rebuild the schedule.

**When does the flow restart (mid-week)?**
- If target role changes Monday–Saturday: flow restarts the **day after**.
- If target role changes on Sunday: flow restarts the **same day** so no learning days are missed.

---

## Flow 3: Lesson Completion & Review Flow

**Goal:** Evaluate learning, update competency, and adapt future learning paths.

```mermaid
flowchart TD
    Start([Lesson / Module\nCompleted by User]) --> S1[1. Planner Triggers Review Generation\nBased on lesson type & competency area]
    S1 --> S2[2. Generate Review\nQuiz / Project / Exercise - Planner]
    S2 --> S3[3. User Takes Review\nQuiz / Project / Exercise]
    S3 --> S4[4. Planner Evaluates Review\nAuto-grade or AI-assisted]
    S4 --> D5{5. Valid Attempt?\nCompleted as expected}
    D5 -- No --> S5A[Request Re-attempt\nor Provide Guidance]
    S5A --> S3
    D5 -- Yes --> S6[6. Evaluate Performance\nScore / Quality / Rubric]
    S6 --> D7{7. Pass Threshold?\nTarget Score or Quality Standard}
    D7 -- Yes --> S7A[Mark as Passed]
    D7 -- No --> S7B[Mark as Not Passed\nProvide Feedback & Recommendations]
    S7B --> S7C[Suggest Remedial\nLessons / Resources - Planner]
    S7C --> S7D[Trigger Replan\nPlanner]
    S7A --> S8[8. Update Competency Estimate\nApply scoring model / confidence adjustment]
    S7D --> S8
    S8 --> S9[9. Update KB\nCompetencies, Progress, Reviews\nStore Review Results]
    S9 --> S10[10. Impact Future Planning\nNext Weekly Cycle]
    S10 --> End([Review Process Complete])
    End -.->|Feeds back into| S1
```

**Feedback loop:** Learn → Review → Update Competency → Adjust Future Learning

**Notes:**
- Reviews can be quizzes, projects, coding exercises, case studies, etc.
- Competency changes drive future learning decisions.
- This is the core feedback loop of the system.
