import base64
import os
from datetime import datetime
from typing import Optional

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session

from ...kb import crud
from ...kb.database import get_session
from ...planner.planner import Planner
from ...scheduler.scheduler import Scheduler, next_sunday

load_dotenv()

router = APIRouter(prefix="/onboard", tags=["onboarding"])

_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_SUPPORTED_DOC_TYPES   = {"application/pdf"}


# ---------------------------------------------------------------------------
# Extract skills from uploaded files (CV / certificate images / PDF)
# ---------------------------------------------------------------------------

class ExtractedSkill(BaseModel):
    skill_name: str
    current_level: int
    target_level: int
    priority: str
    evidence: Optional[str] = None


class ExtractResult(BaseModel):
    skills: list[ExtractedSkill]
    detected_name: Optional[str] = None
    detected_role: Optional[str] = None


@router.post("/extract-skills", response_model=ExtractResult)
async def extract_skills(files: list[UploadFile] = File(...)):
    """Send uploaded CV / certificate files to Claude vision and extract skills."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    content: list[dict] = []
    for f in files:
        raw = await f.read()
        b64 = base64.standard_b64encode(raw).decode()
        mime = f.content_type or "application/octet-stream"

        if mime in _SUPPORTED_IMAGE_TYPES:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })
        elif mime in _SUPPORTED_DOC_TYPES:
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            })
        else:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {mime}. Upload JPEG, PNG, WebP, or PDF.",
            )

    content.append({
        "type": "text",
        "text": (
            "Analyse the uploaded CV / certificates and extract all skills, "
            "technologies, tools, and competencies you can identify. "
            "For each skill estimate the person's current level (1=no knowledge, "
            "3=working knowledge, 5=expert) based on evidence in the document "
            "(years of use, project complexity, certification level). "
            "Also suggest a realistic target level they should aim for. "
            "Call the extract_skills tool."
        ),
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_skills"},
        messages=[{"role": "user", "content": content}],
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    data = tool_use.input
    return ExtractResult(
        skills=[ExtractedSkill(**s) for s in data.get("skills", [])],
        detected_name=data.get("name"),
        detected_role=data.get("current_role"),
    )


# ---------------------------------------------------------------------------
# Full onboarding pipeline
# ---------------------------------------------------------------------------

class SkillEntry(BaseModel):
    skill_name: str
    current_level: int
    target_level: int
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
    first_name: str
    last_name: str
    email: str
    timezone: str
    target_role: str
    skills: list[SkillEntry] = []
    projects: list[ProjectEntry] = []
    certifications: list[CertificationEntry] = []
    learning_style: Optional[str] = None
    weekly_hours: Optional[int] = None
    time_availability: Optional[str] = None
    topics_of_interest: Optional[str] = None
    schedule_this_week: bool = True
    max_lessons_per_cycle: int = 1


class OnboardingResult(BaseModel):
    user_id: int
    target_role: str
    competencies_saved: int
    experience_lessons_added: int
    lessons_generated: int
    lessons_scheduled: int
    no_gaps: bool


@router.post("/", response_model=OnboardingResult)
def onboard(body: OnboardingRequest, session: Session = Depends(get_session)):
    user = crud.get_user(session)
    if user:
        user = crud.update_user(
            session, user.user_id,
            first_name=body.first_name, last_name=body.last_name,
            email=body.email, timezone=body.timezone, target_role=body.target_role,
        )
    else:
        user = crud.create_user(session, body.first_name, body.last_name, body.email, body.timezone)
        crud.set_target_role(session, user.user_id, body.target_role)

    crud.upsert_preferences(
        session, user_id=user.user_id,
        learning_style=body.learning_style, weekly_hours=body.weekly_hours,
        time_availability=body.time_availability, topics_of_interest=body.topics_of_interest,
    )

    for skill in body.skills:
        crud.upsert_competency(
            session, user_id=user.user_id,
            skill_name=skill.skill_name, current_level=skill.current_level,
            target_level=skill.target_level, priority=skill.priority,
        )

    experience_count = 0
    for project in body.projects:
        crud.create_lesson(
            session, topic=project.name, lesson_type="CompletedExperience",
            category=project.tech_used, status="Completed",
            objectives=f"Role: {project.role}. {project.description}",
            evidence_type="Project", completed_date=datetime.utcnow().date(),
        )
        experience_count += 1

    for cert in body.certifications:
        crud.create_lesson(
            session, topic=cert.name, lesson_type="CompletedExperience",
            category=cert.provider, status="Completed",
            objectives=f"Score: {cert.score or 'N/A'}", evidence_type="Certification",
            completed_date=datetime.utcnow().date(),
        )
        experience_count += 1

    plan_result = Planner(session).run_planning_cycle(max_topics=body.max_lessons_per_cycle)

    scheduled_count = 0
    if body.schedule_this_week and plan_result.lessons_created:
        sched_result = Scheduler(session).build_weekly_schedule(next_sunday())
        scheduled_count = sched_result.lessons_scheduled

    return OnboardingResult(
        user_id=user.user_id, target_role=body.target_role,
        competencies_saved=len(body.skills), experience_lessons_added=experience_count,
        lessons_generated=len(plan_result.lessons_created),
        lessons_scheduled=scheduled_count, no_gaps=plan_result.no_gaps,
    )


# ---------------------------------------------------------------------------
# HTML form — 3-step flow
# ---------------------------------------------------------------------------

@router.get("/form", response_class=HTMLResponse)
def onboarding_form(request: Request):
    return HTMLResponse(content=_FORM_HTML)


_FORM_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Learning Scheduler — Onboarding</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1a1a2e}
    .container{max-width:760px;margin:40px auto;padding:0 20px 80px}
    h1{font-size:1.8rem;margin-bottom:4px}
    .subtitle{color:#666;margin-bottom:28px}

    /* Step indicator */
    .steps{display:flex;gap:0;margin-bottom:32px}
    .step{flex:1;text-align:center;padding:10px 4px;font-size:.8rem;font-weight:600;
          color:#aaa;border-bottom:3px solid #e0e0e0;transition:.2s}
    .step.active{color:#3a86ff;border-color:#3a86ff}
    .step.done{color:#22c55e;border-color:#22c55e}

    /* Panels */
    .panel{display:none}
    .panel.visible{display:block}

    section{background:#fff;border-radius:10px;padding:24px;margin-bottom:16px;
            box-shadow:0 1px 4px rgba(0,0,0,.08)}
    h2{font-size:.9rem;font-weight:700;margin-bottom:16px;color:#555;
       text-transform:uppercase;letter-spacing:.06em}
    .field{margin-bottom:14px}
    label{display:block;font-size:.85rem;font-weight:500;margin-bottom:4px}
    input[type=text],input[type=email],input[type=number],select,textarea{
      width:100%;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:.95rem}
    textarea{resize:vertical;min-height:70px}
    .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}

    /* Drop zone */
    .dropzone{border:2px dashed #b0c4de;border-radius:10px;padding:36px 20px;
              text-align:center;cursor:pointer;transition:.2s;background:#fafcff}
    .dropzone:hover,.dropzone.drag{border-color:#3a86ff;background:#eff6ff}
    .dropzone svg{margin-bottom:10px;opacity:.5}
    .dropzone p{color:#666;font-size:.9rem;margin-bottom:8px}
    .dropzone .hint{font-size:.78rem;color:#aaa}
    #fileInput{display:none}
    .file-list{margin-top:12px;display:flex;flex-wrap:wrap;gap:8px}
    .file-chip{background:#eff6ff;border:1px solid #b0c4de;border-radius:20px;
               padding:4px 10px;font-size:.8rem;color:#3a86ff;display:flex;align-items:center;gap:6px}
    .file-chip button{background:none;border:none;cursor:pointer;color:#999;font-size:1rem;line-height:1}

    /* Extract button */
    .extract-btn{width:100%;padding:13px;background:#3a86ff;color:#fff;border:none;
                 border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;margin-top:8px}
    .extract-btn:hover{background:#2563eb}
    .extract-btn:disabled{background:#93c5fd;cursor:not-allowed}

    /* Skills table */
    .skills-table{width:100%;border-collapse:collapse}
    .skills-table th{text-align:left;font-size:.78rem;font-weight:600;color:#888;
                     padding:6px 8px;border-bottom:1px solid #eee;text-transform:uppercase}
    .skills-table td{padding:8px;border-bottom:1px solid #f3f3f3;vertical-align:middle}
    .skills-table tr:last-child td{border-bottom:none}
    .skill-name-cell{font-weight:500;font-size:.9rem}
    .skill-evidence{font-size:.75rem;color:#aaa;margin-top:2px}
    .slider-wrap{display:flex;align-items:center;gap:8px}
    .slider-wrap input[type=range]{flex:1;accent-color:#3a86ff}
    .slider-val{font-weight:700;color:#3a86ff;min-width:18px;text-align:center;font-size:.9rem}
    .priority-sel{padding:4px 6px;border:1px solid #ddd;border-radius:6px;font-size:.82rem}
    .del-btn{background:none;border:none;cursor:pointer;color:#fca5a5;font-size:1.1rem;padding:2px 6px}
    .del-btn:hover{color:#ef4444}

    .add-skill-row{margin-top:12px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;
                   gap:8px;align-items:end}
    .add-skill-row input,.add-skill-row select{padding:6px 8px;border:1px solid #ddd;
                                                border-radius:6px;font-size:.88rem}
    .add-skill-btn{padding:7px 12px;background:#f0f7ff;border:1px solid #3a86ff;
                   border-radius:6px;color:#3a86ff;font-weight:600;cursor:pointer;white-space:nowrap}
    .add-skill-btn:hover{background:#dbeafe}

    /* Nav buttons */
    .nav{display:flex;gap:10px;margin-top:8px}
    .btn-next{flex:1;padding:13px;background:#3a86ff;color:#fff;border:none;
              border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer}
    .btn-next:hover{background:#2563eb}
    .btn-back{padding:13px 22px;background:#f3f4f6;color:#555;border:none;
              border-radius:8px;font-size:1rem;cursor:pointer}
    .btn-back:hover{background:#e5e7eb}

    /* Spinner */
    .spinner{display:inline-block;width:18px;height:18px;border:3px solid rgba(255,255,255,.4);
             border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;
             vertical-align:middle;margin-right:8px}
    @keyframes spin{to{transform:rotate(360deg)}}

    /* Result */
    #result{margin-top:20px;padding:18px;border-radius:8px;display:none}
    #result.success{background:#dcfce7;border:1px solid #86efac}
    #result.error{background:#fee2e2;border:1px solid #fca5a5}

    .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}
    .badge-high{background:#fee2e2;color:#dc2626}
    .badge-medium{background:#fef3c7;color:#d97706}
    .badge-low{background:#dcfce7;color:#16a34a}
    .style-chip{display:flex;align-items:center;gap:6px;padding:8px 14px;border:1px solid #ddd;
                border-radius:20px;cursor:pointer;font-size:.9rem;user-select:none;transition:.15s}
    .style-chip:hover{border-color:#3a86ff;background:#eff6ff}
    .style-chip input{width:auto;accent-color:#3a86ff}
    .avail-table{width:100%;border-collapse:collapse;text-align:center}
    .avail-table th{padding:8px;font-size:.8rem;color:#888;font-weight:600;border-bottom:2px solid #eee}
    .avail-table th span{display:block;font-weight:400;font-size:.73rem;color:#aaa;margin-top:2px}
    .avail-table td{padding:10px 8px;border-bottom:1px solid #f3f3f3}
    .avail-table td:first-child{text-align:left;font-weight:600;font-size:.88rem;color:#555}
    .avail-table input[type=checkbox]{width:18px;height:18px;accent-color:#3a86ff;cursor:pointer}
  </style>
</head>
<body>
<div class="container">
  <h1>Learning Scheduler</h1>
  <p class="subtitle">Set up your personalised learning plan in 3 steps.</p>

  <div class="steps">
    <div class="step active" id="s1">1 · Your Profile</div>
    <div class="step" id="s2">2 · Skills Review</div>
    <div class="step" id="s3">3 · Preferences</div>
  </div>

  <!-- ===== PANEL 1: Profile + Upload ===== -->
  <div class="panel visible" id="panel1">
    <section>
      <h2>Personal Information</h2>
      <div class="row">
        <div class="field"><label>First Name *</label><input id="first_name" value="Noa" required></div>
        <div class="field"><label>Last Name *</label><input id="last_name" value="Kazes" required></div>
      </div>
      <div class="row">
        <div class="field"><label>Email *</label><input id="email" type="email" value="noa.kazes1@gmail.com" required></div>
        <div class="field"><label>Timezone *</label>
          <input id="timezone" value="Asia/Jerusalem" required>
        </div>
      </div>
    </section>

    <section>
      <h2>Target Role</h2>
      <div class="field">
        <label>What role are you working towards? *</label>
        <input id="target_role" value="Data Analyst" required>
      </div>
    </section>

    <section>
      <h2>Upload Your CV & Certificates</h2>
      <p style="font-size:.85rem;color:#666;margin-bottom:14px">
        Upload your CV and any certificate images — the system will extract your skills automatically.
        You'll rate and adjust them in the next step.
      </p>
      <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
        <svg width="40" height="40" fill="none" stroke="#3a86ff" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>
        </svg>
        <p>Drag &amp; drop files here, or click to browse</p>
        <div class="hint">Accepted: PDF, JPG, PNG, WebP &nbsp;·&nbsp; CV, transcripts, certificates</div>
      </div>
      <input type="file" id="fileInput" multiple accept=".pdf,.jpg,.jpeg,.png,.webp">
      <div class="file-list" id="fileList"></div>

      <button class="extract-btn" id="extractBtn" onclick="extractSkills()" style="margin-top:16px">
        Extract My Skills →
      </button>
    </section>
  </div>

  <!-- ===== PANEL 2: Skills Review ===== -->
  <div class="panel" id="panel2">
    <section>
      <h2>Your Skills</h2>
      <p style="font-size:.85rem;color:#666;margin-bottom:16px">
        These skills were extracted from your documents. Adjust the levels, remove anything wrong,
        and add skills that were missed.
      </p>
      <table class="skills-table">
        <thead>
          <tr>
            <th style="width:35%">Skill</th>
            <th style="width:22%">Current level</th>
            <th style="width:22%">Target level</th>
            <th style="width:13%">Priority</th>
            <th style="width:8%"></th>
          </tr>
        </thead>
        <tbody id="skillsBody"></tbody>
      </table>

      <div class="add-skill-row" style="margin-top:16px">
        <input id="newSkillName" placeholder="Skill I missed…">
        <div>
          <label style="font-size:.78rem;color:#888;margin-bottom:2px;display:block">Current</label>
          <input id="newCurrent" type="number" min="1" max="5" value="2" style="width:100%">
        </div>
        <div>
          <label style="font-size:.78rem;color:#888;margin-bottom:2px;display:block">Target</label>
          <input id="newTarget" type="number" min="1" max="5" value="4" style="width:100%">
        </div>
        <select id="newPriority">
          <option value="Medium">Medium</option>
          <option value="High">High</option>
          <option value="Low">Low</option>
        </select>
        <button class="add-skill-btn" onclick="addManualSkill()">+ Add</button>
      </div>
    </section>

    <div class="nav">
      <button class="btn-back" onclick="goTo(1)">← Back</button>
      <button class="btn-next" onclick="goTo(3)">Continue →</button>
    </div>
  </div>

  <!-- ===== PANEL 3: Preferences + Submit ===== -->
  <div class="panel" id="panel3">

    <section>
      <h2>Learning Style</h2>
      <p style="font-size:.83rem;color:#666;margin-bottom:12px">Select all that apply.</p>
      <div style="display:flex;flex-wrap:wrap;gap:10px">
        <label class="style-chip"><input type="checkbox" value="Visual"> 🎨 Visual</label>
        <label class="style-chip"><input type="checkbox" value="Reading"> 📖 Reading</label>
        <label class="style-chip"><input type="checkbox" value="Hands-on"> 💻 Hands-on</label>
        <label class="style-chip"><input type="checkbox" value="Video"> 🎬 Video</label>
        <label class="style-chip"><input type="checkbox" value="Audio"> 🎧 Audio</label>
      </div>
    </section>

    <section>
      <h2>Available Time Slots</h2>
      <p style="font-size:.83rem;color:#666;margin-bottom:14px">
        Tick the blocks when you are typically free to study.
        The scheduler will only book lessons in these windows.
      </p>
      <button type="button" class="add-btn" style="margin-bottom:12px" onclick="sameForAll()">
        Apply Sunday's selection to all days
      </button>
      <table class="avail-table">
        <thead>
          <tr>
            <th></th>
            <th>Morning<br><span>09:00–12:30</span></th>
            <th>Afternoon<br><span>13:30–16:30</span></th>
            <th>Evening<br><span>17:00–20:00</span></th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Sun</td><td><input type="checkbox" class="avail" data-day="Sun" data-block="morning" checked></td><td><input type="checkbox" class="avail" data-day="Sun" data-block="afternoon" checked></td><td><input type="checkbox" class="avail" data-day="Sun" data-block="evening"></td></tr>
          <tr><td>Mon</td><td><input type="checkbox" class="avail" data-day="Mon" data-block="morning" checked></td><td><input type="checkbox" class="avail" data-day="Mon" data-block="afternoon" checked></td><td><input type="checkbox" class="avail" data-day="Mon" data-block="evening"></td></tr>
          <tr><td>Tue</td><td><input type="checkbox" class="avail" data-day="Tue" data-block="morning" checked></td><td><input type="checkbox" class="avail" data-day="Tue" data-block="afternoon" checked></td><td><input type="checkbox" class="avail" data-day="Tue" data-block="evening"></td></tr>
          <tr><td>Wed</td><td><input type="checkbox" class="avail" data-day="Wed" data-block="morning" checked></td><td><input type="checkbox" class="avail" data-day="Wed" data-block="afternoon" checked></td><td><input type="checkbox" class="avail" data-day="Wed" data-block="evening"></td></tr>
          <tr><td>Thu</td><td><input type="checkbox" class="avail" data-day="Thu" data-block="morning" checked></td><td><input type="checkbox" class="avail" data-day="Thu" data-block="afternoon" checked></td><td><input type="checkbox" class="avail" data-day="Thu" data-block="evening"></td></tr>
        </tbody>
      </table>
    </section>

    <section>
      <h2>Scheduling</h2>
      <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
        <input type="checkbox" id="schedule_this_week" checked style="width:auto">
        <span style="font-weight:500">Book my lessons into Google Calendar</span>
      </label>
      <p style="font-size:.83rem;color:#666;margin-top:8px;padding-left:28px">
        After onboarding, the system will scan your Google Calendar for free slots within
        your selected time blocks above and automatically book your first lessons as calendar events.
        You can reschedule or delete them like any other event.
        Leave this unchecked if you prefer to schedule manually later.
      </p>
    </section>

    <div class="nav">
      <button class="btn-back" onclick="goTo(2)">← Back</button>
      <button class="btn-next" id="submitBtn" onclick="submitOnboarding()">
        Generate My Learning Plan →
      </button>
    </div>
  </div>

  <div id="result"></div>
</div>

<script>
  // ─── File management ───────────────────────────────────────────────────────
  let selectedFiles = [];

  document.getElementById('fileInput').addEventListener('change', e => {
    addFiles([...e.target.files]);
    e.target.value = '';
  });

  const dz = document.getElementById('dropzone');
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('drag');
    addFiles([...e.dataTransfer.files]);
  });

  function addFiles(files) {
    files.forEach(f => {
      if (!selectedFiles.find(x => x.name === f.name && x.size === f.size))
        selectedFiles.push(f);
    });
    renderFileList();
  }

  function removeFile(name) {
    selectedFiles = selectedFiles.filter(f => f.name !== name);
    renderFileList();
  }

  function renderFileList() {
    const el = document.getElementById('fileList');
    el.innerHTML = selectedFiles.map(f => `
      <div class="file-chip">
        📄 ${f.name}
        <button onclick="removeFile('${f.name.replace(/'/g,"\\'")}')">×</button>
      </div>`).join('');
  }

  // ─── Step navigation ───────────────────────────────────────────────────────
  function goTo(n) {
    if (n === 1 && !validatePanel1()) return;
    [1,2,3].forEach(i => {
      document.getElementById('panel'+i).classList.toggle('visible', i===n);
      const s = document.getElementById('s'+i);
      s.classList.remove('active','done');
      if (i === n) s.classList.add('active');
      if (i < n)  s.classList.add('done');
    });
    window.scrollTo({top:0,behavior:'smooth'});
  }

  function validatePanel1() {
    const required = ['first_name','last_name','email','timezone','target_role'];
    for (const id of required) {
      if (!document.getElementById(id).value.trim()) {
        document.getElementById(id).focus();
        return false;
      }
    }
    return true;
  }

  // ─── Extract skills ────────────────────────────────────────────────────────
  let extractedSkills = [];   // [{skill_name, current_level, target_level, priority, evidence}]

  async function extractSkills() {
    if (!validatePanel1()) return;

    const btn = document.getElementById('extractBtn');

    if (selectedFiles.length === 0) {
      // No files — go to step 2 with empty table so user can add manually
      renderSkillsTable([]);
      goTo(2);
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Extracting skills…';

    try {
      const form = new FormData();
      selectedFiles.forEach(f => form.append('files', f));

      const res = await fetch('/onboard/extract-skills', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Extraction failed');
      }
      const data = await res.json();

      // Pre-fill name if detected and fields are empty
      if (data.detected_name) {
        const parts = data.detected_name.trim().split(' ');
        if (!document.getElementById('first_name').value && parts.length >= 1)
          document.getElementById('first_name').value = parts[0];
        if (!document.getElementById('last_name').value && parts.length >= 2)
          document.getElementById('last_name').value = parts.slice(1).join(' ');
      }
      if (data.detected_role && !document.getElementById('target_role').value)
        document.getElementById('target_role').value = data.detected_role;

      extractedSkills = data.skills;
      renderSkillsTable(extractedSkills);
      goTo(2);
    } catch(e) {
      alert('Error: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Extract My Skills →';
    }
  }

  // ─── Skills table ──────────────────────────────────────────────────────────
  function renderSkillsTable(skills) {
    extractedSkills = skills;
    const tbody = document.getElementById('skillsBody');
    tbody.innerHTML = skills.length
      ? skills.map((s, i) => skillRow(s, i)).join('')
      : '<tr><td colspan="5" style="padding:20px;text-align:center;color:#aaa">No skills extracted yet — add them manually below.</td></tr>';
  }

  function skillRow(s, i) {
    const pri = s.priority || 'Medium';
    return `<tr id="row-${i}">
      <td>
        <div class="skill-name-cell">${escHtml(s.skill_name)}</div>
        ${s.evidence ? `<div class="skill-evidence">${escHtml(s.evidence)}</div>` : ''}
      </td>
      <td>
        <div class="slider-wrap">
          <input type="range" min="1" max="5" value="${s.current_level}"
            oninput="this.nextElementSibling.textContent=this.value" id="cur-${i}">
          <span class="slider-val">${s.current_level}</span>
        </div>
      </td>
      <td>
        <div class="slider-wrap">
          <input type="range" min="1" max="5" value="${s.target_level}"
            oninput="this.nextElementSibling.textContent=this.value" id="tgt-${i}">
          <span class="slider-val">${s.target_level}</span>
        </div>
      </td>
      <td>
        <select class="priority-sel" id="pri-${i}">
          ${['High','Medium','Low'].map(p =>
            `<option${p===pri?' selected':''}>${p}</option>`).join('')}
        </select>
      </td>
      <td><button class="del-btn" onclick="deleteSkill(${i})">✕</button></td>
    </tr>`;
  }

  function deleteSkill(i) {
    extractedSkills.splice(i, 1);
    renderSkillsTable(extractedSkills);
  }

  function addManualSkill() {
    const name = document.getElementById('newSkillName').value.trim();
    if (!name) { document.getElementById('newSkillName').focus(); return; }
    extractedSkills.push({
      skill_name: name,
      current_level: parseInt(document.getElementById('newCurrent').value) || 2,
      target_level:  parseInt(document.getElementById('newTarget').value)  || 4,
      priority: document.getElementById('newPriority').value,
      evidence: null,
    });
    renderSkillsTable(extractedSkills);
    document.getElementById('newSkillName').value = '';
  }

  function readSkillsFromTable() {
    return extractedSkills.map((s, i) => {
      const curEl = document.getElementById('cur-'+i);
      const tgtEl = document.getElementById('tgt-'+i);
      const priEl = document.getElementById('pri-'+i);
      return {
        skill_name:    s.skill_name,
        current_level: curEl ? parseInt(curEl.value) : s.current_level,
        target_level:  tgtEl ? parseInt(tgtEl.value) : s.target_level,
        priority:      priEl ? priEl.value : (s.priority || 'Medium'),
      };
    });
  }

  // ─── Learning style ────────────────────────────────────────────────────────
  function readLearningStyles() {
    const checked = [...document.querySelectorAll('.style-chip input:checked')]
      .map(el => el.value);
    return checked.length ? checked.join(',') : '';
  }

  // ─── Time availability grid ────────────────────────────────────────────────
  function readAvailability() {
    const result = {};
    document.querySelectorAll('.avail').forEach(cb => {
      const day = cb.dataset.day;
      if (!result[day]) result[day] = [];
      if (cb.checked) result[day].push(cb.dataset.block);
    });
    return result;
  }

  function sameForAll() {
    const sunBlocks = [...document.querySelectorAll('.avail[data-day="Sun"]')]
      .map(cb => ({ block: cb.dataset.block, checked: cb.checked }));
    ['Mon','Tue','Wed','Thu'].forEach(day => {
      sunBlocks.forEach(({ block, checked }) => {
        const cb = document.querySelector(`.avail[data-day="${day}"][data-block="${block}"]`);
        if (cb) cb.checked = checked;
      });
    });
  }

  // ─── Final submit ──────────────────────────────────────────────────────────
  async function submitOnboarding() {
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Building your plan…';

    const payload = {
      first_name:        document.getElementById('first_name').value.trim(),
      last_name:         document.getElementById('last_name').value.trim(),
      email:             document.getElementById('email').value.trim(),
      timezone:          document.getElementById('timezone').value.trim(),
      target_role:       document.getElementById('target_role').value.trim(),
      learning_style:    readLearningStyles() || null,
      weekly_hours:      null,
      time_availability: JSON.stringify(readAvailability()),
      topics_of_interest: null,
      schedule_this_week:document.getElementById('schedule_this_week').checked,
      skills: readSkillsFromTable(),
      projects: [],
      certifications: [],
    };

    const resultEl = document.getElementById('result');
    resultEl.style.display = 'none';

    try {
      const res = await fetch('/onboard/', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      clearDraft();
      resultEl.className = 'success';
      resultEl.innerHTML = `
        <strong>✓ Onboarding complete!</strong><br><br>
        Target role: <strong>${data.target_role}</strong><br>
        Skills saved: ${data.competencies_saved}<br>
        Lessons generated: ${data.lessons_generated}<br>
        Lessons scheduled in calendar: ${data.lessons_scheduled}
        ${data.no_gaps
          ? '<br><br><em>No skill gaps found — consider setting a more ambitious target role.</em>'
          : ''}`;
      resultEl.style.display = 'block';
      window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});
    } catch(e) {
      resultEl.className = 'error';
      resultEl.innerHTML = `<strong>Error:</strong> ${e.message}`;
      resultEl.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Generate My Learning Plan →';
    }
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ─── localStorage save / restore ──────────────────────────────────────────
  const LS_KEY = 'onboarding_draft';
  const SAVED_FIELDS = ['first_name','last_name','email','timezone','target_role'];

  function saveDraft() {
    const draft = {};
    SAVED_FIELDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) draft[id] = el.value;
    });
    // Learning style checkboxes
    draft.learning_styles = [...document.querySelectorAll('.style-chip input:checked')]
      .map(el => el.value);
    // Time availability grid
    draft.availability = {};
    document.querySelectorAll('.avail').forEach(cb => {
      const day = cb.dataset.day;
      if (!draft.availability[day]) draft.availability[day] = {};
      draft.availability[day][cb.dataset.block] = cb.checked;
    });
    localStorage.setItem(LS_KEY, JSON.stringify(draft));
  }

  function restoreDraft() {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    try {
      const draft = JSON.parse(raw);
      SAVED_FIELDS.forEach(id => {
        const el = document.getElementById(id);
        if (el && draft[id] !== undefined) el.value = draft[id];
      });
      if (draft.learning_styles) {
        document.querySelectorAll('.style-chip input').forEach(cb => {
          cb.checked = draft.learning_styles.includes(cb.value);
        });
      }
      if (draft.availability) {
        document.querySelectorAll('.avail').forEach(cb => {
          const day = cb.dataset.day;
          const block = cb.dataset.block;
          if (draft.availability[day] && draft.availability[day][block] !== undefined)
            cb.checked = draft.availability[day][block];
        });
      }
    } catch(e) {}
  }

  function clearDraft() {
    localStorage.removeItem(LS_KEY);
  }

  // Auto-save on any input change
  document.addEventListener('input', saveDraft);
  document.addEventListener('change', saveDraft);

  // Restore on load
  restoreDraft();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Claude tool definition for skill extraction
# ---------------------------------------------------------------------------

_EXTRACT_TOOL = {
    "name": "extract_skills",
    "description": (
        "Extract skills, technologies, tools and competencies from a CV or certificate. "
        "Estimate current proficiency level from evidence (years of use, project complexity, "
        "certification grade). Suggest a realistic target level."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill or technology",
                        },
                        "current_level": {
                            "type": "integer",
                            "minimum": 1, "maximum": 5,
                            "description": "Estimated current level: 1=no knowledge, 3=working knowledge, 5=expert",
                        },
                        "target_level": {
                            "type": "integer",
                            "minimum": 1, "maximum": 5,
                            "description": "Realistic target level to aim for",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low"],
                            "description": "Suggested learning priority",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "One short sentence explaining what in the document suggests this skill level",
                        },
                    },
                    "required": ["skill_name", "current_level", "target_level", "priority"],
                },
            },
            "name": {
                "type": "string",
                "description": "Person's full name if visible in the document",
            },
            "current_role": {
                "type": "string",
                "description": "Current or most recent job title if visible",
            },
        },
        "required": ["skills"],
    },
}
