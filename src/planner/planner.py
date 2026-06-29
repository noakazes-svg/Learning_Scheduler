import os

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlmodel import Session

from ..kb import crud
from ..kb.models import Review
from ..scraper.scraper import Scraper
from ..scheduler.scheduler import Scheduler, current_week_sunday

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOPICS_PER_CYCLE = 3


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class TopicPlan(BaseModel):
    skill_name: str
    topic: str               # specific sub-topic for one lesson
    learning_path_title: str
    rationale: str


class PlanningResult(BaseModel):
    learning_paths_created: list[str]
    lessons_created: list[int]   # lesson IDs
    skipped_topics: list[str]
    no_gaps: bool = False        # True when no competency gaps were found


class ReviewContent(BaseModel):
    review_type: str             # Quiz | Project | Exercise | Assessment
    instructions: str
    questions: list[str]
    exercises: list[dict]


class ReviewEvaluation(BaseModel):
    score: float
    max_score: float
    passed: bool
    feedback: str
    suggestions: list[str]
    competency_delta: int        # suggested change: -1, 0, or +1


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class Planner:
    def __init__(self, session: Session):
        self.session = session
        self.scraper = Scraper()
        self.claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ------------------------------------------------------------------
    # Planning cycle
    # ------------------------------------------------------------------

    def run_planning_cycle(self, max_topics: int = MAX_TOPICS_PER_CYCLE) -> PlanningResult:
        """Analyze competency gaps, create learning paths, and generate lessons."""
        user = crud.get_user(self.session)
        if not user:
            raise ValueError("No user found in KB.")

        gaps = crud.get_competency_gaps(self.session, user.user_id)
        if not gaps:
            # Task 8: no gaps found — signal caller to prompt user for a more aspirational role
            return PlanningResult(
                learning_paths_created=[], lessons_created=[], skipped_topics=[], no_gaps=True
            )

        gap_summary = "\n".join(
            f"- {g.skill_name}: level {g.current_level}/5 → target {g.target_level}/5"
            f"{f', priority: {g.priority}' if g.priority else ''}"
            for g in gaps
        )

        response = self.claude.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[_PRIORITIZE_TOOL],
            tool_choice={"type": "tool", "name": "prioritize_topics"},
            messages=[{
                "role": "user",
                "content": (
                    f"The user has these competency gaps:\n{gap_summary}\n\n"
                    f"Select the top {max_topics} most impactful topics to address. "
                    "Break each skill into one specific, concrete sub-topic suitable "
                    "for a single self-study lesson (30–90 min)."
                ),
            }],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        topic_plans = [
            TopicPlan(**t) for t in tool_use.input.get("topics", [])
        ][:max_topics]

        paths_created: list[str] = []
        lessons_created: list[int] = []
        skipped: list[str] = []

        for plan in topic_plans:
            # Get or create the learning path for this skill
            existing = crud.get_learning_paths(self.session, user.user_id)
            path = next((p for p in existing if p.title == plan.learning_path_title), None)
            if not path:
                path = crud.create_learning_path(
                    self.session, user.user_id, plan.learning_path_title
                )
                paths_created.append(plan.learning_path_title)

            # Task 7: skip if prerequisites are not yet met
            if not crud.prerequisites_met(self.session, path.learning_path_id):
                skipped.append(f"{plan.topic}: prerequisites not completed")
                continue

            # Scraper assembles the lesson
            try:
                assembled = self.scraper.assemble_lesson(
                    topic=plan.topic,
                    context=f"Skill: {plan.skill_name}. {plan.rationale}",
                )
            except Exception as exc:
                skipped.append(f"{plan.topic}: {exc}")
                continue

            lesson = crud.create_lesson(
                self.session,
                topic=assembled.topic,
                lesson_type="PlannedLesson",
                learning_path_id=path.learning_path_id,
                category=assembled.category,
                difficulty=assembled.difficulty,
                duration_minutes=assembled.duration_minutes,
                objectives="\n".join(assembled.objectives),
                source=", ".join(assembled.sources),
                content=assembled.content,
            )
            lessons_created.append(lesson.lesson_id)

        return PlanningResult(
            learning_paths_created=paths_created,
            lessons_created=lessons_created,
            skipped_topics=skipped,
        )

    # ------------------------------------------------------------------
    # Review generation
    # ------------------------------------------------------------------

    def generate_review(self, lesson_id: int) -> tuple[Review, ReviewContent]:
        """Generate a review for a completed lesson and persist it."""
        lesson = crud.get_lesson(self.session, lesson_id)
        if not lesson:
            raise ValueError(f"Lesson {lesson_id} not found.")

        lesson_content = crud.load_lesson_content(lesson_id) or ""

        response = self.claude.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[_REVIEW_GEN_TOOL],
            tool_choice={"type": "tool", "name": "generate_review"},
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a review for this lesson.\n\n"
                    f"Topic: {lesson.topic}\n"
                    f"Category: {lesson.category or 'General'}\n"
                    f"Difficulty: {lesson.difficulty or 'Intermediate'}\n\n"
                    f"Lesson content:\n{lesson_content}"
                ),
            }],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        review_content = ReviewContent(**tool_use.input)

        review = crud.create_review(self.session, lesson_id, review_content.review_type)
        crud.save_review_content(review.review_id, review_content.model_dump())

        return review, review_content

    # ------------------------------------------------------------------
    # Review evaluation
    # ------------------------------------------------------------------

    def evaluate_review(self, review_id: int, submission: str) -> ReviewEvaluation:
        """Evaluate a user's submission against the review and store the result."""
        raw = crud.load_review_content(review_id)
        if not raw:
            raise ValueError(f"Review content not found for review {review_id}.")

        review_content = ReviewContent(**raw)

        questions_block = "\n".join(f"- {q}" for q in review_content.questions)
        exercises_block = "\n".join(
            f"- {e.get('title', '')}: {e.get('description', '')}"
            for e in review_content.exercises
        )

        response = self.claude.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[_EVALUATE_TOOL],
            tool_choice={"type": "tool", "name": "evaluate_submission"},
            messages=[{
                "role": "user",
                "content": (
                    f"Review type: {review_content.review_type}\n"
                    f"Instructions: {review_content.instructions}\n"
                    f"Questions:\n{questions_block}\n"
                    f"Exercises:\n{exercises_block}\n\n"
                    f"User submission:\n{submission}"
                ),
            }],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        evaluation = ReviewEvaluation(**tool_use.input)

        crud.create_review_result(
            self.session,
            review_id=review_id,
            score=evaluation.score,
            max_score=evaluation.max_score,
            passed=evaluation.passed,
            feedback=evaluation.feedback,
        )

        return evaluation

    # ------------------------------------------------------------------
    # Competency update
    # ------------------------------------------------------------------

    def apply_competency_delta(self, competency_id: int, delta: int) -> None:
        """Adjust a competency's current_level by delta, clamped to 1–5."""
        from ..kb.models import Competency
        comp = self.session.get(Competency, competency_id)
        if comp:
            new_level = max(1, min(5, comp.current_level + delta))
            crud.update_competency_level(self.session, competency_id, new_level)

    # Task 9 ----------------------------------------------------------------

    def replan_after_failed_review(self, lesson_id: int) -> PlanningResult:
        """Generate remedial lessons for the failed lesson's topic and kick off a new cycle."""
        lesson = crud.get_lesson(self.session, lesson_id)
        if not lesson:
            raise ValueError(f"Lesson {lesson_id} not found.")

        # Lower the current_level for the matching competency to widen the gap
        user = crud.get_user(self.session)
        if user:
            comps = crud.get_competencies(self.session, user.user_id)
            for comp in comps:
                if comp.skill_name.lower() == (lesson.category or "").lower():
                    new_level = max(1, comp.current_level - 1)
                    crud.update_competency_level(self.session, comp.competency_id, new_level)
                    break

        result = self.run_planning_cycle(max_topics=1)
        if result.lessons_created:
            Scheduler(self.session).build_weekly_schedule(current_week_sunday())
        return result

    # Task 10 ---------------------------------------------------------------

    def replan_on_role_change(self, new_target_role: str) -> PlanningResult:
        """Update the user's target role and trigger an immediate replan."""
        user = crud.get_user(self.session)
        if not user:
            raise ValueError("No user found.")
        crud.set_target_role(self.session, user.user_id, new_target_role)
        result = self.run_planning_cycle()
        if result.lessons_created:
            Scheduler(self.session).build_weekly_schedule(current_week_sunday())
        return result


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------

_PRIORITIZE_TOOL = {
    "name": "prioritize_topics",
    "description": "Return a prioritized list of specific lesson topics to address competency gaps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "The competency this topic addresses",
                        },
                        "topic": {
                            "type": "string",
                            "description": "Specific sub-topic for a single lesson, e.g. 'SQL Window Functions'",
                        },
                        "learning_path_title": {
                            "type": "string",
                            "description": "Name of the learning path this lesson belongs to",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this topic was prioritized",
                        },
                    },
                    "required": ["skill_name", "topic", "learning_path_title", "rationale"],
                },
            }
        },
        "required": ["topics"],
    },
}

_REVIEW_GEN_TOOL = {
    "name": "generate_review",
    "description": "Generate a review (quiz, project, or exercise) for a completed lesson.",
    "input_schema": {
        "type": "object",
        "properties": {
            "review_type": {
                "type": "string",
                "enum": ["Quiz", "Project", "Exercise", "Assessment"],
            },
            "instructions": {
                "type": "string",
                "description": "Clear instructions for the learner",
            },
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–5 comprehension or application questions (for Quiz/Assessment)",
            },
            "exercises": {
                "type": "array",
                "description": "1–2 practical exercises (for Project/Exercise)",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["coding", "written", "project", "quiz"],
                        },
                    },
                    "required": ["title", "description", "type"],
                },
            },
        },
        "required": ["review_type", "instructions", "questions", "exercises"],
    },
}

_EVALUATE_TOOL = {
    "name": "evaluate_submission",
    "description": "Evaluate a learner's review submission and return a score and feedback.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "description": "Points earned",
            },
            "max_score": {
                "type": "number",
                "description": "Maximum possible points",
            },
            "passed": {
                "type": "boolean",
                "description": "True if the learner demonstrated sufficient understanding",
            },
            "feedback": {
                "type": "string",
                "description": "Specific, constructive feedback on the submission",
            },
            "suggestions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2–3 concrete suggestions for improvement or next steps",
            },
            "competency_delta": {
                "type": "integer",
                "enum": [-1, 0, 1],
                "description": (
                    "Suggested change to the learner's competency level: "
                    "+1 if clearly demonstrated mastery, 0 if adequate, -1 if significant gaps remain"
                ),
            },
        },
        "required": ["score", "max_score", "passed", "feedback", "suggestions", "competency_delta"],
    },
}
