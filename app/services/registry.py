import sqlite3
import json
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from app.models.schemas import (
    EventOutput, ContactOutput, MeetingSummaryOutput, 
    TaskExtractionOutput, JobDescriptionOutput
)

class PromptVersion(BaseModel):
    id: str
    name: str
    version: int
    template: str
    description: Optional[str] = None
    schema_def: Optional[Dict[str, Any]] = None

class PromptRegistry:
    def __init__(self, db_path: str = "registry.db"):
        self.db_path = db_path
        self._shared_conn = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
        self._init_db()
        if db_path != ":memory:":
            self.seed_production_templates()

    def _get_conn(self):
        if self._shared_conn:
            return self._shared_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT,
                    name TEXT,
                    version INTEGER,
                    template TEXT,
                    description TEXT,
                    schema_def TEXT,
                    PRIMARY KEY (name, version)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_id TEXT,
                    model_used TEXT,
                    total_cases INTEGER,
                    passed_cases INTEGER,
                    pass_rate_pct REAL,
                    avg_latency_ms REAL,
                    total_tokens INTEGER,
                    total_cost REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    breakdown_json TEXT
                )
            ''')
            conn.commit()
        finally:
            if not self._shared_conn:
                conn.close()

    def seed_production_templates(self):
        """Seed the 5 core production prompt templates with Pydantic JSON schemas."""
        templates_to_seed = [
            {
                "name": "event_extraction",
                "template": "Extract event details from the text:\n\nText: {{ text }}\n\nReturn JSON adhering to schema.",
                "description": "v1 - Basic Event Extraction",
                "schema_def": EventOutput.model_json_schema()
            },
            {
                "name": "event_extraction",
                "template": (
                    "You are a professional executive calendar assistant.\n"
                    "Carefully extract all event scheduling details from this announcement:\n\n"
                    "Announcement:\n{{ text }}\n\n"
                    "Provide explicit structured details including title, date, time, venue/virtual location, and attendee list."
                ),
                "description": "v2 - Comprehensive Executive Event Scheduler with Attendees & Timing",
                "schema_def": EventOutput.model_json_schema()
            },
            {
                "name": "contact_extraction",
                "template": (
                    "You are a CRM contact ingestion engine.\n"
                    "Parse the messy contact info, email signature, or biography below and extract contact fields:\n\n"
                    "Raw Content:\n{{ text }}\n\n"
                    "Extract full name, email, phone, company, job title, and social links."
                ),
                "description": "v1 - CRM Contact & Lead Ingestion Engine",
                "schema_def": ContactOutput.model_json_schema()
            },
            {
                "name": "meeting_summary",
                "template": (
                    "You are an AI chief of staff.\n"
                    "Summarize the following meeting transcript into actionable minutes:\n\n"
                    "Transcript:\n{{ transcript }}\n\n"
                    "Extract the meeting title, date, key discussion points, decisions made, and assigned action items with owners."
                ),
                "description": "v1 - Meeting Minutes & Action Item Extractor",
                "schema_def": MeetingSummaryOutput.model_json_schema()
            },
            {
                "name": "task_extraction",
                "template": (
                    "You are an agile project manager.\n"
                    "Analyze the product notes or team chat below and generate structured sprint tasks:\n\n"
                    "Sprint Notes:\n{{ notes }}\n\n"
                    "Extract project name and individual tasks with IDs (TASK-1, TASK-2), priority, assignee, and estimated hours."
                ),
                "description": "v1 - Agile Sprint Task & Backlog Generator",
                "schema_def": TaskExtractionOutput.model_json_schema()
            },
            {
                "name": "job_parser",
                "template": (
                    "You are an ATS (Applicant Tracking System) parser.\n"
                    "Analyze this raw job vacancy listing and extract key hiring criteria:\n\n"
                    "Job Posting:\n{{ job_post }}\n\n"
                    "Extract job title, company, location, employment type, experience level, salary range, required skills, and responsibilities."
                ),
                "description": "v1 - ATS Job Vacancy & Skill Extraction Parser",
                "schema_def": JobDescriptionOutput.model_json_schema()
            },
        ]

        conn = self._get_conn()
        try:
            cur = conn.cursor()
            for t in templates_to_seed:
                cur.execute("SELECT id FROM prompts WHERE name = ? AND description = ?", (t["name"], t["description"]))
                if not cur.fetchone():
                    cur.execute("SELECT MAX(version) FROM prompts WHERE name = ?", (t["name"],))
                    row = cur.fetchone()
                    version = (row[0] or 0) + 1
                    prompt_id = f"{t['name']}_v{version}"
                    cur.execute('''
                        INSERT INTO prompts (id, name, version, template, description, schema_def)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (prompt_id, t["name"], version, t["template"], t["description"], json.dumps(t["schema_def"])))
                    conn.commit()
        finally:
            if not self._shared_conn:
                conn.close()

    def add_prompt(self, name: str, template: str, description: str = "", schema_def: Optional[Dict[str, Any]] = None) -> PromptVersion:
        clean_name = name.strip()
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT MAX(version) FROM prompts WHERE name = ?", (clean_name,))
            row = cur.fetchone()
            version = (row[0] or 0) + 1
            prompt_id = f"{clean_name}_v{version}"
            
            cur.execute('''
                INSERT INTO prompts (id, name, version, template, description, schema_def)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (prompt_id, clean_name, version, template, description, json.dumps(schema_def) if schema_def else None))
            conn.commit()
            
            return PromptVersion(
                id=prompt_id,
                name=clean_name,
                version=version,
                template=template,
                description=description,
                schema_def=schema_def
            )
        finally:
            if not self._shared_conn:
                conn.close()

    def get_prompt(self, name: str, version: Optional[int] = None) -> Optional[PromptVersion]:
        clean_name = name.strip()
        if "_v" in clean_name and version is None:
            parts = clean_name.rsplit("_v", 1)
            if len(parts) == 2 and parts[1].isdigit():
                clean_name = parts[0]
                version = int(parts[1])

        conn = self._get_conn()
        try:
            cur = conn.cursor()
            if version is not None:
                cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts WHERE name = ? AND version = ?", (clean_name, version))
            else:
                cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts WHERE name = ? ORDER BY version DESC LIMIT 1", (clean_name,))
            
            row = cur.fetchone()
            if not row:
                return None
                
            return PromptVersion(
                id=row[0],
                name=row[1],
                version=row[2],
                template=row[3],
                description=row[4],
                schema_def=json.loads(row[5]) if row[5] else None
            )
        finally:
            if not self._shared_conn:
                conn.close()

    def list_all_prompts(self) -> List[PromptVersion]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts ORDER BY name ASC, version DESC")
            rows = cur.fetchall()
            return [
                PromptVersion(
                    id=r[0], name=r[1], version=r[2], template=r[3], description=r[4],
                    schema_def=json.loads(r[5]) if r[5] else None
                )
                for r in rows
            ]
        finally:
            if not self._shared_conn:
                conn.close()

    def log_evaluation(
        self,
        prompt_id: str,
        model_used: str,
        total_cases: int,
        passed_cases: int,
        pass_rate_pct: float,
        avg_latency_ms: float,
        total_tokens: int,
        total_cost: float,
        breakdown_json: str
    ):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO evaluations (
                    prompt_id, model_used, total_cases, passed_cases, 
                    pass_rate_pct, avg_latency_ms, total_tokens, total_cost, breakdown_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (prompt_id, model_used, total_cases, passed_cases, pass_rate_pct, avg_latency_ms, total_tokens, total_cost, breakdown_json))
            conn.commit()
        finally:
            if not self._shared_conn:
                conn.close()

    def get_evaluation_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT id, prompt_id, model_used, total_cases, passed_cases, 
                       pass_rate_pct, avg_latency_ms, total_tokens, total_cost, created_at, breakdown_json
                FROM evaluations ORDER BY id DESC LIMIT ?
            ''', (limit,))
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "prompt_id": r[1],
                    "model_used": r[2],
                    "total_cases": r[3],
                    "passed_cases": r[4],
                    "pass_rate_pct": r[5],
                    "avg_latency_ms": r[6],
                    "total_tokens": r[7],
                    "total_cost": r[8],
                    "created_at": r[9],
                    "breakdown": json.loads(r[10]) if r[10] else []
                }
                for r in rows
            ]
        finally:
            if not self._shared_conn:
                conn.close()
