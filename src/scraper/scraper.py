import os
from typing import Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel
from tavily import TavilyClient

load_dotenv()

MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class Exercise(BaseModel):
    title: str
    description: str
    type: str  # coding | written | project | quiz


class Resource(BaseModel):
    title: str
    url: str
    resource_type: str  # article | video | course | docs | tool


class AssembledLesson(BaseModel):
    topic: str
    category: str
    difficulty: str          # Beginner | Intermediate | Advanced
    duration_minutes: int
    task_type: str           # reading | video | practice | project | podcast
    objectives: list[str]
    action_steps: list[str]  # concrete things to DO, with links where relevant
    resources: list[Resource]
    content: str             # Full lesson in markdown
    exercises: list[Exercise]
    review_questions: list[str] = []
    sources: list[str]


class JobListing(BaseModel):
    title: str
    company: Optional[str] = None
    description: str
    required_skills: list[str]
    url: str


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class Scraper:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        self.claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def assemble_lesson(
        self,
        topic: str,
        context: str = "",
        preferred_type: Optional[str] = None,
    ) -> AssembledLesson:
        """Search for material on a topic and assemble it into a structured lesson.

        preferred_type: 'video' | 'podcast' | 'practice' | 'project' | 'reading'
        When provided, shapes the search query and system prompt to produce content
        in that format. If omitted, Claude chooses the best format.
        """
        _SEARCH_QUERIES = {
            "video":   f"{topic} youtube tutorial video course watch",
            "podcast": f"{topic} overview introduction concepts explained in-depth",
        }
        search_query = _SEARCH_QUERIES.get(preferred_type or "", f"{topic} tutorial guide learn")

        results = self.tavily.search(
            query=search_query,
            search_depth="basic",
            max_results=3,
            include_raw_content=False,
        )

        search_context = "\n\n".join(
            f"Source: {r['url']}\nTitle: {r['title']}\n{r.get('content', '')}"
            for r in results.get("results", [])
        )

        if not search_context.strip():
            raise ValueError(f"No search results found for topic: {topic}")

        raw_results = results.get("results", [])
        sources = [r["url"] for r in raw_results]

        _TYPE_INSTRUCTIONS = {
            "video": (
                "This is a VIDEO lesson. "
                "action_steps must all be in the format 'Watch: [Title] at [url]'. "
                "Find and link to real YouTube tutorials or online courses from the research material. "
                "The content section should include timestamps or chapters to focus on, "
                "and a note-taking framework ('What to look for'). "
                "Set task_type to 'video'. Duration 45–90 minutes."
            ),
            "podcast": (
                "This is a PODCAST/AUDIO lesson. "
                "The 'content' field is the SOURCE DOCUMENT that will be uploaded to NotebookLM "
                "to auto-generate an audio podcast — so fill it with rich, narrative, "
                "conversational text covering the topic in depth (like a magazine feature or "
                "book chapter). The content MUST be long and detailed — at least 800 words. "
                "Do NOT include 'open terminal' or coding steps in the content. "
                "action_steps should say: 'Upload this lesson file to notebooklm.google.com "
                "and click Generate Audio Overview to create your podcast'. "
                "Objectives and review_questions should be conceptual. "
                "Set task_type to 'podcast'. Duration 35–45 minutes."
            ),
        }
        type_instruction = _TYPE_INSTRUCTIONS.get(preferred_type or "", "")

        system_prompt = (
            "You are an expert instructional designer. Given research material, "
            "create a complete, well-structured lesson for a professional learner. "
            "Include concrete action steps the learner must perform (e.g. 'Watch X at [url]', "
            "'Complete this Kaggle notebook', 'Read section Y'). "
            "Always include the real URLs from the research material as resources. "
            "Use markdown for the content. Be practical and specific."
            + (f"\n\n{type_instruction}" if type_instruction else "")
        )

        user_message = (
            f"Topic: {topic}\n"
            + (f"Learning context: {context}\n" if context else "")
            + f"\nResearch material (use these URLs as direct resources):\n{search_context}"
        )

        response = self.claude.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=[_LESSON_TOOL],
            tool_choice={"type": "tool", "name": "create_lesson"},
            messages=[{"role": "user", "content": user_message}],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input
        return AssembledLesson(
            topic=topic,
            sources=sources,
            exercises=[Exercise(**e) for e in data.pop("exercises", [])],
            resources=[Resource(**r) for r in data.pop("resources", [])],
            **data,
        )

    def search_job_listings(self, role: str, max_results: int = 5) -> list[JobListing]:
        """Search for public job listings for a role and return structured data."""
        results = self.tavily.search(
            query=f"{role} job description requirements skills",
            search_depth="advanced",
            max_results=max_results,
        )

        search_context = "\n\n".join(
            f"URL: {r['url']}\nTitle: {r['title']}\n{r.get('content', '')}"
            for r in results.get("results", [])
        )

        if not search_context.strip():
            return []

        response = self.claude.messages.create(
            model=MODEL,
            max_tokens=2048,
            tools=[_JOB_LISTINGS_TOOL],
            tool_choice={"type": "tool", "name": "extract_job_listings"},
            messages=[{
                "role": "user",
                "content": (
                    f"Extract structured job listing data for the role: {role}\n\n"
                    f"Search results:\n{search_context}"
                ),
            }],
        )

        tool_use = next(b for b in response.content if b.type == "tool_use")
        return [JobListing(**item) for item in tool_use.input.get("listings", [])]


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------

_LESSON_TOOL = {
    "name": "create_lesson",
    "description": "Create a structured lesson from research material.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Subject area, e.g. Python, SQL, Data Analysis, Machine Learning",
            },
            "difficulty": {
                "type": "string",
                "enum": ["Beginner", "Intermediate", "Advanced"],
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Estimated minutes to complete the lesson",
            },
            "task_type": {
                "type": "string",
                "enum": ["reading", "video", "practice", "project", "podcast"],
                "description": "Primary activity type: reading=articles/docs, video=watch tutorials, practice=coding exercises, project=build something, podcast=listen",
            },
            "objectives": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2–4 clear learning objectives",
            },
            "action_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–5 concrete steps the learner must perform, e.g. 'Watch [Title] at https://...', 'Complete exercise X', 'Read section Y at https://...'",
            },
            "resources": {
                "type": "array",
                "description": "2–4 direct links from the research material",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "resource_type": {
                            "type": "string",
                            "enum": ["article", "video", "course", "docs", "tool"],
                        },
                    },
                    "required": ["title", "url", "resource_type"],
                },
            },
            "content": {
                "type": "string",
                "description": "Full lesson content in markdown. Include explanations, examples, and code snippets. Reference the resources inline with markdown links.",
            },
            "exercises": {
                "type": "array",
                "description": "1–3 practical exercises",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "type": {"type": "string", "enum": ["coding", "written", "project", "quiz"]},
                    },
                    "required": ["title", "description", "type"],
                },
            },
            "review_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–5 questions to assess understanding",
            },
        },
        "required": [
            "category", "difficulty", "duration_minutes", "task_type",
            "objectives", "action_steps", "resources", "content", "exercises",
        ],
    },
}

_JOB_LISTINGS_TOOL = {
    "name": "extract_job_listings",
    "description": "Extract structured job listing data from search results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "listings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "company": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "Summary of the role and its responsibilities",
                        },
                        "required_skills": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "url": {"type": "string"},
                    },
                    "required": ["title", "description", "required_skills", "url"],
                },
            }
        },
        "required": ["listings"],
    },
}
