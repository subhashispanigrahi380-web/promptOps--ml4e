import hashlib
import json
import time
from typing import Any, Dict, Optional

# Simple in-memory cache: key -> (response_dict, timestamp)
_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 300  # Cache valid for 5 minutes

def _make_key(prompt_id: str, variables: Dict, task_type: Optional[str]) -> str:
    raw = json.dumps({"prompt_id": prompt_id, "variables": variables, "task_type": task_type}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def get_cached(prompt_id: str, variables: Dict, task_type: Optional[str]) -> Optional[Any]:
    key = _make_key(prompt_id, variables, task_type)
    entry = _cache.get(key)
    if entry:
        response, ts = entry
        if time.time() - ts < CACHE_TTL_SECONDS:
            return response  # Cache hit
        else:
            del _cache[key]  # Expired
    return None  # Cache miss

def set_cache(prompt_id: str, variables: Dict, task_type: Optional[str], response: Any):
    key = _make_key(prompt_id, variables, task_type)
    _cache[key] = (response, time.time())

def cache_stats() -> Dict:
    return {"cached_entries": len(_cache), "ttl_seconds": CACHE_TTL_SECONDS}
