import asyncio
import time
import re
from typing import Dict, Any, Optional, List, AsyncGenerator
from app.services.providers.base import LLMProvider
from app.models.schemas import GenerationResponse, UsageStats

class MockProvider(LLMProvider):
    """
    Intelligent heuristic mock provider. 
    Rather than returning hardcoded static placeholders, this provider dynamically
    parses and extracts entities directly from the user's input prompt so that
    different inputs yield distinctly different, relevant, schema-conforming outputs.
    """
    def __init__(self, delay_ms: int = 150):
        self.delay_ms = delay_ms

    def _extract_title(self, text: str) -> str:
        # Check for explicit keywords
        m = re.search(r'(?:about|for|hosting|announcing|titled|event|meeting|call)\s+([A-Za-z0-9\s&—\-]{4,40}?)(?=[.,\n]|\s+on|\s+at|\s+with)', text, re.I)
        if m and len(m.group(1).strip()) > 3:
            return m.group(1).strip().title()
        # Fall back to first non-empty line or clause
        first_line = text.strip().split('\n')[0].split('.')[0]
        cleaned = re.sub(r'^(hey team|hi all|join us for|update:|quick note:?)\s*', '', first_line, flags=re.I).strip()
        if len(cleaned) > 3:
            return cleaned[:45].strip().title()
        return "Extracted Event Title"

    def _extract_date(self, text: str) -> str:
        # Search for months or date patterns
        m = re.search(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b', text, re.I)
        if m:
            return m.group(0)
        # Search for relative days
        m_rel = re.search(r'\b(next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|this\s+friday|tomorrow|every\s+monday)\b', text, re.I)
        if m_rel:
            return m_rel.group(0).title()
        # ISO / digit format
        m_iso = re.search(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b', text)
        if m_iso:
            return m_iso.group(0)
        return "2026-11-20"

    def _extract_time(self, text: str) -> str:
        m = re.search(r'\b\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\s*(?:to|-)\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\b(?:\s*[A-Z]{3,4})?', text)
        if m:
            return m.group(0)
        m_single = re.search(r'\b\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\b(?:\s*[A-Z]{3,4})?', text)
        if m_single:
            return m_single.group(0)
        return "10:00 AM - 12:00 PM"

    def _extract_location(self, text: str) -> str:
        m = re.search(r'(?:at|in|venue:)\s+([A-Za-z0-9\s,\-\.]{3,40}?)(?=[.,\n]|\s+on|\s+from|\s+with|\s+speakers)', text, re.I)
        if m:
            loc = m.group(1).strip()
            if loc.lower() not in ("9", "10", "11", "12", "the", "a", "an", "all", "our"):
                if "zoom" in text.lower() or "virtual" in text.lower() or "teams" in text.lower():
                    return f"{loc.title()} (Zoom Livestream)"
                return loc.title()
        if "zoom" in text.lower() or "virtual" in text.lower() or "google meet" in text.lower():
            return "Virtual Meeting (Zoom / Google Meet)"
        return "Main Conference Hall"

    def _extract_attendees(self, text: str) -> List[str]:
        # Search for speakers/attendees lists
        m = re.search(r'(?:speakers|attendees|with|host|keynotes?|assigned to|leads?)\s*[:by\s]+([^\.\n]+)', text, re.I)
        if m:
            raw_list = m.group(1)
            # Split by comma or 'and'
            names = re.split(r',|\band\b|&', raw_list)
            cleaned_names = [re.sub(r'[^A-Za-z\s\.]', '', n).strip().title() for n in names if len(n.strip()) > 2]
            valid_names = [n for n in cleaned_names if n.lower() not in ("team", "folks", "all", "register", "early")]
            if valid_names:
                return valid_names[:5]
        # Search for capitalized Name pairs (e.g. Andrew Ng, Sarah Connor)
        pairs = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+))\b', text)
        good_pairs = [p for p in pairs if p.lower() not in ("annual ai", "cloud summit", "convention center", "moscone center", "zoom livestream", "product launch", "san francisco", "austin texas")]
        if good_pairs:
            return list(dict.fromkeys(good_pairs))[:4]
        return ["Alex Rivera", "Jordan Smith"]

    def _extract_email(self, text: str) -> str:
        m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        return m.group(0) if m else "contact@promptops.ai"

    def _extract_phone(self, text: str) -> str:
        m = re.search(r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}', text)
        return m.group(0) if m else "+1 (415) 890-1234"

    def _extract_organization(self, text: str) -> str:
        m = re.search(r'(?:at|company:?|with|from)\s+([A-Z][A-Za-z0-9\s&]+(?:Corp|Inc|LLC|Systems|Technologies|Group|Solutions|Bio|AI|Labs)?)\b', text)
        if m:
            org = m.group(1).strip()
            if len(org) > 2 and org.lower() not in ("9", "the", "a", "zoom", "our"):
                return org.title()
        return "PromptOps AI Systems"

    def _extract_key_points(self, text: str) -> List[str]:
        sentences = [s.strip() for s in re.split(r'[.\n;]', text) if len(s.strip()) > 10]
        if len(sentences) >= 2:
            return [f"Key finding: {s}" for s in sentences[:3]]
        return [f"Review of {text[:40]}...", "Agreed on project execution timeline", "Aligned on architecture requirements"]

    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> GenerationResponse:
        start = time.time()
        await asyncio.sleep(self.delay_ms / 1000.0)

        # Dynamic extraction from user's actual prompt text
        content: Any = {}
        if json_schema and "properties" in json_schema:
            props = json_schema["properties"]
            for key, spec in props.items():
                t = spec.get("type", "string")
                k_lower = key.lower()

                if t == "string":
                    if "title" in k_lower or "name" in k_lower and "full" not in k_lower and "company" not in k_lower:
                        content[key] = self._extract_title(prompt)
                    elif "full_name" in k_lower or "contact" in k_lower:
                        attendees = self._extract_attendees(prompt)
                        content[key] = attendees[0] if attendees else "Dr. Elena Rostova"
                    elif "date" in k_lower:
                        content[key] = self._extract_date(prompt)
                    elif "time" in k_lower:
                        content[key] = self._extract_time(prompt)
                    elif "location" in k_lower or "venue" in k_lower:
                        content[key] = self._extract_location(prompt)
                    elif "email" in k_lower:
                        content[key] = self._extract_email(prompt)
                    elif "phone" in k_lower:
                        content[key] = self._extract_phone(prompt)
                    elif "organization" in k_lower or "company" in k_lower:
                        content[key] = self._extract_organization(prompt)
                    elif "job_title" in k_lower or "role" in k_lower:
                        m_role = re.search(r'\b(Senior\s+[A-Za-z\s]+Engineer|Developer|Manager|Scientist|Architect|VP\s+of\s+[A-Za-z\s]+)\b', prompt, re.I)
                        content[key] = m_role.group(0).title() if m_role else "Lead AI Systems Engineer"
                    elif "salary" in k_lower or "compensation" in k_lower:
                        m_sal = re.search(r'\$[\d,kK]+(?:\s*-\s*\$[\d,kK]+)?', prompt)
                        content[key] = m_sal.group(0) if m_sal else "$165,000 - $210,000 USD"
                    elif "experience" in k_lower:
                        m_exp = re.search(r'\d+\+?\s+years?', prompt, re.I)
                        content[key] = f"{m_exp.group(0)} experience" if m_exp else "Mid to Senior Level (5+ years)"
                    elif "description" in k_lower or "summary" in k_lower or "overview" in k_lower:
                        # Extract first meaningful sentence
                        first_sentence = prompt.strip().split('\n')[0].split('.')[0]
                        content[key] = f"Extracted details for: {first_sentence[:80].strip()}"
                    else:
                        content[key] = f"Extracted {key.replace('_', ' ').title()}"

                elif t == "array":
                    items_spec = spec.get("items", {})
                    if items_spec.get("type") == "object":
                        sub_props = items_spec.get("properties", {})
                        if "task" in k_lower or "action" in k_lower:
                            # Generate structured action items from input text
                            tasks = []
                            m_tasks = re.findall(r'(?:TASK-\d+|\d+\.)\s*([^\n\.,]+)', prompt)
                            if m_tasks:
                                for idx, t_desc in enumerate(m_tasks[:3], 1):
                                    tasks.append({
                                        "task_id": f"TASK-{idx}",
                                        "description": t_desc.strip(),
                                        "priority": "High" if idx == 1 else "Medium",
                                        "assignee": "Lead Engineer",
                                        "estimated_hours": 3.0 * idx,
                                        "task": t_desc.strip(),
                                        "owner": "Engineer",
                                        "due_date": "Next Sprint"
                                    })
                            else:
                                tasks = [
                                    {"task_id": "TASK-1", "task": f"Implement {prompt[:30].strip()}...", "description": f"Execute action item from {prompt[:35]}...", "owner": "Assigned Lead", "priority": "High", "assignee": "Alex", "estimated_hours": 4.0, "due_date": "Friday"}
                                ]
                            content[key] = tasks
                        else:
                            content[key] = [{k: f"Item for {k}" for k in sub_props.keys()}]
                    else:
                        if "attendee" in k_lower or "speaker" in k_lower or "people" in k_lower:
                            content[key] = self._extract_attendees(prompt)
                        elif "skill" in k_lower or "requirements" in k_lower:
                            # Extract programming languages / skills
                            found_skills = []
                            for tech in ["Python", "FastAPI", "Docker", "AsyncIO", "PostgreSQL", "Kubernetes", "PyTorch", "LiteLLM", "AWS", "GCP"]:
                                if tech.lower() in prompt.lower():
                                    found_skills.append(tech)
                            content[key] = found_skills if found_skills else ["Python", "FastAPI", "Docker"]
                        elif "discussion" in k_lower or "decision" in k_lower:
                            content[key] = self._extract_key_points(prompt)
                        else:
                            content[key] = [f"Item 1 from {prompt[:20]}...", "Item 2"]

                elif t in ("number", "integer"):
                    m_num = re.search(r'\b\d+(?:\.\d+)?\b', prompt)
                    content[key] = float(m_num.group(0)) if m_num else 4.0
                elif t == "boolean":
                    content[key] = True
                else:
                    content[key] = f"Dynamic {key}"
        else:
            content = f"Extracted completion for: {prompt[:60]}..."

        latency = int((time.time() - start) * 1000)
        tokens_est = max(45, len(prompt) // 4)
        return GenerationResponse(
            content=content,
            usage=UsageStats(prompt_tokens=tokens_est, completion_tokens=85, total_tokens=tokens_est + 85, estimated_cost=0.0),
            latency_ms=latency,
            model_used=model_override or "mock-intelligent-extractor",
            validation_status="PASSED",
            retry_count=0
        )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        chunks = [f"Extraction result for:\n", f"{prompt[:40]}...\n", "Completed successfully.\n"]
        for c in chunks:
            await asyncio.sleep(0.04)
            yield c
