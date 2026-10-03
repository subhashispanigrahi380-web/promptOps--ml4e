from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Union

class GenerationRequest(BaseModel):
    prompt_id: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
    task_type: Optional[str] = None  # 'extraction', 'complex_reasoning', 'mock'

class UsageStats(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0

class GenerationResponse(BaseModel):
    content: Union[str, Dict[str, Any]]
    usage: UsageStats
    latency_ms: int
    model_used: str
    cached: bool = False
    error: Optional[str] = None
