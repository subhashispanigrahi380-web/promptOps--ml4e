from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union

# ==============================================================================
# 1. Domain Schemas for Structured Generation Templates
# ==============================================================================

class EventOutput(BaseModel):
    title: str = Field(description="Name or title of the event")
    date: str = Field(description="Date of the event in YYYY-MM-DD or readable format")
    time: Optional[str] = Field(default="TBD", description="Start and end time of the event")
    location: Optional[str] = Field(default="Virtual / TBD", description="Physical venue or virtual meeting link")
    description: Optional[str] = Field(default="", description="Summary of event purpose")
    attendees: List[str] = Field(default_factory=list, description="List of attendees, speakers, or organizers")

class ContactOutput(BaseModel):
    full_name: str = Field(description="Full name of the contact person")
    email: Optional[str] = Field(default=None, description="Email address")
    phone: Optional[str] = Field(default=None, description="Phone or mobile number")
    organization: Optional[str] = Field(default=None, description="Company, university, or organization name")
    job_title: Optional[str] = Field(default=None, description="Job title or professional role")
    social_links: List[str] = Field(default_factory=list, description="LinkedIn, Twitter, GitHub, or website links")

class ActionItem(BaseModel):
    task: str = Field(description="Action item description")
    owner: Optional[str] = Field(default="Unassigned", description="Person responsible for the task")
    due_date: Optional[str] = Field(default="TBD", description="Target completion date")

class MeetingSummaryOutput(BaseModel):
    meeting_title: str = Field(description="Title or topic of the meeting")
    date: Optional[str] = Field(default="Unknown", description="Meeting date")
    key_discussion_points: List[str] = Field(default_factory=list, description="Key topics discussed")
    decisions_made: List[str] = Field(default_factory=list, description="Decisions agreed upon during the meeting")
    action_items: List[ActionItem] = Field(default_factory=list, description="Tasks and next steps assigned")

class ExtractedTask(BaseModel):
    task_id: str = Field(description="Unique task identifier, e.g., TASK-1")
    description: str = Field(description="Detailed task instruction")
    priority: str = Field(default="Medium", description="Priority level: High, Medium, or Low")
    assignee: Optional[str] = Field(default="Unassigned", description="Assigned developer or team member")
    estimated_hours: Optional[float] = Field(default=1.0, description="Estimated effort in hours")

class TaskExtractionOutput(BaseModel):
    project_name: Optional[str] = Field(default="General Project", description="Project or sprint name")
    tasks: List[ExtractedTask] = Field(default_factory=list, description="List of extracted actionable tasks")

class JobDescriptionOutput(BaseModel):
    job_title: str = Field(description="Title of the role")
    company: str = Field(description="Hiring company or organization")
    location: str = Field(default="Remote", description="Office location or Remote status")
    employment_type: str = Field(default="Full-time", description="Full-time, Part-time, Contract, or Internship")
    experience_level: Optional[str] = Field(default="Mid-Level", description="Entry-level, Mid-level, Senior, Lead, or Executive")
    salary_range: Optional[str] = Field(default="Competitive / Not specified", description="Compensation or salary band")
    required_skills: List[str] = Field(default_factory=list, description="Must-have technical and soft skills")
    key_responsibilities: List[str] = Field(default_factory=list, description="Primary duties and responsibilities")

# Mapping helper from template name to schema class
DOMAIN_SCHEMA_MAP = {
    "event_extraction": EventOutput,
    "contact_extraction": ContactOutput,
    "meeting_summary": MeetingSummaryOutput,
    "task_extraction": TaskExtractionOutput,
    "job_parser": JobDescriptionOutput,
}

# ==============================================================================
# 2. Telemetry and API Request / Response Schemas
# ==============================================================================

class UsageStats(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0

class GenerationRequest(BaseModel):
    prompt_id: str = Field(description="Prompt identifier or name, e.g., event_extraction_v1")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variables to inject into Jinja2 template")
    task_type: Optional[str] = Field(default="gemini", description="Provider route: gemini, groq, openai, or mock")
    model_override: Optional[str] = Field(default=None, description="Optional custom model name")
    api_key_override: Optional[str] = Field(default=None, description="Optional runtime API key")
    stream: bool = Field(default=False, description="Streaming mode flag")
    max_retries: int = Field(default=2, description="Max auto-repair retry attempts on validation failure")

class GenerationResponse(BaseModel):
    content: Union[Dict[str, Any], str] = Field(description="Structured JSON result or generated text")
    usage: UsageStats = Field(default_factory=UsageStats, description="Token consumption and cost telemetry")
    latency_ms: int = Field(default=0, description="Roundtrip processing time in milliseconds")
    model_used: str = Field(default="unknown", description="Model identifier used for inference")
    cached: bool = Field(default=False, description="Whether output was served from high-speed cache")
    validation_status: str = Field(default="PASSED", description="PASSED, AUTO_REPAIRED, FAILED, or SKIPPED")
    retry_count: int = Field(default=0, description="Number of repair retries required")
    validation_errors: List[str] = Field(default_factory=list, description="Validation issues encountered if any")
    error: Optional[str] = Field(default=None, description="Fatal execution error message if failed")
    prompt_id: Optional[str] = Field(default=None, description="Resolved prompt ID")
    prompt_version: Optional[int] = Field(default=None, description="Resolved prompt version")

# ==============================================================================
# 3. Prompt Evaluation Benchmark Schemas
# ==============================================================================

class EvaluationCase(BaseModel):
    name: str
    variables: Dict[str, Any]
    required_keys: List[str] = Field(default_factory=list)

class EvaluationRecord(BaseModel):
    id: Optional[int] = None
    prompt_id: str
    model_used: str
    total_cases: int
    passed_cases: int
    pass_rate_pct: float
    avg_latency_ms: float
    total_tokens: int
    total_cost: float
    created_at: str
    breakdown_json: str
