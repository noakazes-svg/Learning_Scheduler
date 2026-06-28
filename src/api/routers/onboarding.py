from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session

from ...kb import crud
from ...kb.database import get_session
from ...planner.planner import Planner
from ...scheduler.scheduler import Scheduler, next_monday

router = APIRouter(prefix="/onboard", tags=["onboarding"])


# ---------------------------------------------------------------------------
# Request schema (Flow 1 web form inputs)
# ---------------------------------------------------------------------------

class SkillEntry(BaseModel):
    skill_name: str
    current_level: int   # 1–5
    target_level: int    # 1–5
    priority: Optional[str] = None


class ProjectEntry(BaseModel):
    name: str
    description: str
    role: str
    tech_used: str


class CertificationEntry(BaseModel):
    name: str
    provider: str
    date_completed: Optional[str] = None
    score: Optional[str] = None


class OnboardingRequest(BaseModel):
    # Personal & Background
    first_name: str
    last_name: str
    email: str
    timezone: str
    role_summary: Optional[str] = None

    # Target
    target_role: str

    # Skills
    skills: list[SkillEntry] = []

    # Past experience stored as CompletedExperience lessons
    projects: list[ProjectEntry] = []
    certifications: list[CertificationEntry] = []

    # Preferences
    learning_style: Optional[str] = None
    weekly_hours: Optional[int] = None
    time_availability: Optional[str] = None
    topics_of_interest: Optional[str] = None

    # Planning options
    schedule_this_week: bool = True
    max_lessons_per_cycle: int = 3


class OnboardingResult(BaseModel):
    user_id: int
    target_role: str
    competencies_saved: int
    experience_lessons_added: int
    lessons_generated: int
    lessons_scheduled: int
    no_gaps: bool


# ---------------------------------------------------------------------------
# POST /onboard — full Flow 1 pipeline
# ---------------------------------------------------------------------------

@router.post("/", response_model=OnboardingResult)
def onboard(body: OnboardingRequest, session: Session = Depends(get_session)):
    # 1. Create or update user
    user = crud.get_user(session)
    if user:
        user = crud.update_user(
            session, user.user_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            timezone=body.timezone,
            target_role=body.target_role,
        )
    else:
        user = crud.create_user(session, body.first_name, body.last_name, body.email, body.timezone)
        crud.set_target_role(session, user.user_id, body.target_role)

    # 2. Save preferences
    crud.upsert_preferences(
        session,
        user_id=user.user_id,
        learning_style=body.learning_style,
        weekly_hours=body.weekly_hours,
        time_availability=body.time_availability,
        topics_of_interest=body.topics_of_interest,
    )

    # 3. Self-assessment — upsert competencies
    for skill in body.skills:
        crud.upsert_competency(
            session,
            user_id=user.user_id,
            skill_name=skill.skill_name,
            current_level=skill.current_level,
            target_level=skill.target_level,
            priority=skill.priority,
        )

    # 4. Store past experience as CompletedExperience lessons
    experience_count = 0
    for project in body.projects:
        crud.create_lesson(
            session,
            topic=project.name,
            lesson_type="CompletedExperience",
            category=project.tech_used,
            status="Completed",
            objectives=f"Role: {project.role}. {project.description}",
            evidence_type="Project",
            completed_date=datetime.utcnow().date(),
        )
        experience_count += 1

    for cert in body.certifications:
        crud.create_lesson(
            session,
            topic=cert.name,
            lesson_type="CompletedExperience",
            category=cert.provider,
            status="Completed",
            objectives=f"Score: {cert.score or 'N/A'}",
            evidence_type="Certification",
            evidence_date=datetime.strptime(cert.date_completed, "%Y-%m-%d").date()
            if cert.date_completed else None,
            completed_date=datetime.utcnow().date(),
        )
        experience_count += 1

    # 5. Gap analysis + lesson generation (Planner)
    planner = Planner(session)
    plan_result = planner.run_planning_cycle(max_topics=body.max_lessons_per_cycle)

    # 6. Schedule (if requested and lessons were generated)
    scheduled_count = 0
    if body.schedule_this_week and plan_result.lessons_created:
        sched_result = Scheduler(session).build_weekly_schedule(next_monday())
        scheduled_count = sched_result.lessons_scheduled

    return OnboardingResult(
        user_id=user.user_id,
        target_role=body.target_role,
        competencies_saved=len(body.skills),
        experience_lessons_added=experience_count,
        lessons_generated=len(plan_result.lessons_created),
        lessons_scheduled=scheduled_count,
        no_gaps=plan_result.no_gaps,
    )


# ---------------------------------------------------------------------------
# GET /onboard/form — HTML onboarding form (Task 6)
# ---------------------------------------------------------------------------

@router.get("/form", response_class=HTMLResponse)
def onboarding_form(request: Request):
    return HTMLResponse(content=_FORM_HTML)


_FORM_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Learning Scheduler — Onboarding</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f7fa; color: #1a1a2e; }
    .container { max-width: 740px; margin: 40px auto; padding: 0 20px 60px; }
    h1 { font-size: 1.8rem; margin-bottom: 4px; }
    .subtitle { color: #666; margin-bottom: 32px; }
    section { background: #fff; border-radius: 10px; padding: 24px; margin-bottom: 20px;
              box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: #444; text-transform: uppercase;
         letter-spacing: .05em; }
    .field { margin-bottom: 14px; }
    label { display: block; font-size: .85rem; font-weight: 500; margin-bottom: 4px; }
    input, select, textarea { width: 100%; padding: 8px 10px; border: 1px solid #ddd;
                              border-radius: 6px; font-size: .95rem; }
    textarea { resize: vertical; min-height: 72px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .skill-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 8px;
                 margin-bottom: 8px; align-items: end; }
    .skill-row label { font-size: .8rem; }
    .add-btn { background: none; border: 1px dashed #aaa; border-radius: 6px; padding: 6px 14px;
               cursor: pointer; font-size: .85rem; color: #666; margin-top: 4px; }
    .add-btn:hover { background: #f0f0f0; }
    .submit-btn { width: 100%; padding: 14px; background: #3a86ff; color: #fff; border: none;
                  border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer;
                  margin-top: 8px; }
    .submit-btn:hover { background: #2563eb; }
    #result { margin-top: 20px; padding: 16px; border-radius: 8px; display: none; }
    #result.success { background: #dcfce7; border: 1px solid #86efac; }
    #result.error   { background: #fee2e2; border: 1px solid #fca5a5; }
  </style>
</head>
<body>
<div class="container">
  <h1>Learning Scheduler</h1>
  <p class="subtitle">Fill in your profile to generate your personalised learning plan.</p>

  <form id="onboardForm">

    <section>
      <h2>Personal Information</h2>
      <div class="row">
        <div class="field"><label>First Name *</label><input name="first_name" required></div>
        <div class="field"><label>Last Name *</label><input name="last_name" required></div>
      </div>
      <div class="row">
        <div class="field"><label>Email *</label><input name="email" type="email" required></div>
        <div class="field"><label>Timezone *</label>
          <input name="timezone" placeholder="e.g. Asia/Jerusalem" required>
        </div>
      </div>
    </section>

    <section>
      <h2>Target Role</h2>
      <div class="field">
        <label>Desired Role *</label>
        <input name="target_role" placeholder="e.g. Data Analyst, ML Engineer" required>
      </div>
    </section>

    <section>
      <h2>Self-Assessment — Rate Your Skills</h2>
      <p style="font-size:.85rem;color:#666;margin-bottom:12px">
        1 = No knowledge &nbsp;·&nbsp; 3 = Working knowledge &nbsp;·&nbsp; 5 = Expert
      </p>
      <div id="skillsContainer">
        <div class="skill-row">
          <div><label>Skill Name</label><input class="skill-name" placeholder="e.g. Python"></div>
          <div><label>Current (1–5)</label><input class="skill-current" type="number" min="1" max="5" value="1"></div>
          <div><label>Target (1–5)</label><input class="skill-target" type="number" min="1" max="5" value="3"></div>
          <div><label>Priority</label>
            <select class="skill-priority">
              <option value="">—</option>
              <option>High</option><option>Medium</option><option>Low</option>
            </select>
          </div>
        </div>
      </div>
      <button type="button" class="add-btn" onclick="addSkillRow()">+ Add skill</button>
    </section>

    <section>
      <h2>Past Projects</h2>
      <div id="projectsContainer"></div>
      <button type="button" class="add-btn" onclick="addProjectRow()">+ Add project</button>
    </section>

    <section>
      <h2>Courses & Certifications</h2>
      <div id="certsContainer"></div>
      <button type="button" class="add-btn" onclick="addCertRow()">+ Add certification</button>
    </section>

    <section>
      <h2>Preferences</h2>
      <div class="row">
        <div class="field"><label>Learning Style</label>
          <select name="learning_style">
            <option value="">—</option>
            <option>Visual</option><option>Reading</option><option>Hands-on</option>
          </select>
        </div>
        <div class="field"><label>Weekly Hours Available</label>
          <input name="weekly_hours" type="number" min="1" max="40" placeholder="e.g. 10">
        </div>
      </div>
      <div class="row">
        <div class="field"><label>Time of Day</label>
          <select name="time_availability">
            <option value="">—</option>
            <option>Mornings</option><option>Afternoons</option>
            <option>Evenings</option><option>Flexible</option>
          </select>
        </div>
        <div class="field"><label>Topics of Interest</label>
          <input name="topics_of_interest" placeholder="e.g. AI, SQL, Cloud">
        </div>
      </div>
    </section>

    <div class="field" style="margin-top:8px">
      <label>
        <input type="checkbox" name="schedule_this_week" checked>
        Schedule lessons into my Google Calendar for next week
      </label>
    </div>

    <button type="submit" class="submit-btn">Generate My Learning Plan →</button>
  </form>

  <div id="result"></div>
</div>

<script>
function addSkillRow() {
  const div = document.createElement('div');
  div.className = 'skill-row';
  div.innerHTML = `
    <div><input class="skill-name" placeholder="Skill name"></div>
    <div><input class="skill-current" type="number" min="1" max="5" value="1"></div>
    <div><input class="skill-target" type="number" min="1" max="5" value="3"></div>
    <div><select class="skill-priority">
      <option value="">—</option><option>High</option><option>Medium</option><option>Low</option>
    </select></div>`;
  document.getElementById('skillsContainer').appendChild(div);
}

function addProjectRow() {
  const div = document.createElement('div');
  div.style.marginBottom = '12px';
  div.innerHTML = `
    <div class="row" style="margin-bottom:6px">
      <div><input class="proj-name" placeholder="Project name"></div>
      <div><input class="proj-role" placeholder="Your role"></div>
    </div>
    <input class="proj-tech" placeholder="Technologies used" style="margin-bottom:6px">
    <textarea class="proj-desc" placeholder="Brief description" rows="2"></textarea>`;
  document.getElementById('projectsContainer').appendChild(div);
}

function addCertRow() {
  const div = document.createElement('div');
  div.className = 'row';
  div.style.marginBottom = '8px';
  div.innerHTML = `
    <div><input class="cert-name" placeholder="Certification / Course name"></div>
    <div><input class="cert-provider" placeholder="Provider (e.g. Coursera)"></div>`;
  document.getElementById('certsContainer').appendChild(div);
}

document.getElementById('onboardForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;

  const skills = [...document.querySelectorAll('.skill-name')]
    .map((el, i) => ({
      skill_name: el.value,
      current_level: parseInt(document.querySelectorAll('.skill-current')[i].value),
      target_level: parseInt(document.querySelectorAll('.skill-target')[i].value),
      priority: document.querySelectorAll('.skill-priority')[i].value || null,
    }))
    .filter(s => s.skill_name.trim());

  const projects = [...document.querySelectorAll('.proj-name')]
    .map((el, i) => ({
      name: el.value,
      role: document.querySelectorAll('.proj-role')[i].value,
      tech_used: document.querySelectorAll('.proj-tech')[i].value,
      description: document.querySelectorAll('.proj-desc')[i].value,
    }))
    .filter(p => p.name.trim());

  const certifications = [...document.querySelectorAll('.cert-name')]
    .map((el, i) => ({
      name: el.value,
      provider: document.querySelectorAll('.cert-provider')[i].value,
    }))
    .filter(c => c.name.trim());

  const payload = {
    first_name: f.first_name.value,
    last_name: f.last_name.value,
    email: f.email.value,
    timezone: f.timezone.value,
    target_role: f.target_role.value,
    learning_style: f.learning_style.value || null,
    weekly_hours: f.weekly_hours.value ? parseInt(f.weekly_hours.value) : null,
    time_availability: f.time_availability.value || null,
    topics_of_interest: f.topics_of_interest.value || null,
    schedule_this_week: f.schedule_this_week.checked,
    skills,
    projects,
    certifications,
  };

  const resultEl = document.getElementById('result');
  resultEl.style.display = 'none';

  try {
    const res = await fetch('/onboard/', { method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json();

    if (!res.ok) throw new Error(data.detail || 'Server error');

    resultEl.className = 'success';
    resultEl.innerHTML = `
      <strong>✓ Onboarding complete!</strong><br>
      Target role: <strong>${data.target_role}</strong><br>
      Competencies saved: ${data.competencies_saved}<br>
      Lessons generated: ${data.lessons_generated}<br>
      Lessons scheduled: ${data.lessons_scheduled}
      ${data.no_gaps ? '<br><em>No skill gaps found — consider setting a more ambitious target role.</em>' : ''}`;
    resultEl.style.display = 'block';
  } catch (err) {
    resultEl.className = 'error';
    resultEl.innerHTML = `<strong>Error:</strong> ${err.message}`;
    resultEl.style.display = 'block';
  }
});
</script>
</body>
</html>
"""
