# Failure Log

Documents every known failure mode, edge case, and how the platform handles it.

## 1. Malformed JSON from Model
**Trigger:** Model returns `{bad_json: true` instead of valid JSON.  
**Test:** `tests/test_generation.py::test_repair_loop_fixes_malformed_json`  
**Behaviour:** Caught by `OutputValidator`, error appended to prompt, retried. Recovered on attempt 2.  
**Status:** ✅ Auto-repaired

---

## 2. Permanently Invalid Output (All Retries Exhausted)
**Trigger:** Model ignores schema on every attempt.  
**Test:** `tests/test_generation.py::test_repair_loop_gives_up_eventually`  
**Behaviour:** After `max_retries` attempts, returns `GenerationResponse` with `error` field populated.  
**Status:** ✅ Graceful failure — no crash

---

## 3. Provider Timeout
**Trigger:** Model takes too long / network unavailable.  
**Test:** `tests/test_generation.py::test_timeout_handling`  
**Behaviour:** Provider returns error string `"Request timed out"`. Propagated clearly to caller.  
**Status:** ✅ Handled

---

## 4. Invalid JSON in Variables Input (UI)
**Trigger:** User types malformed JSON in the Variables box.  
**Behaviour:** Streamlit catches `json.JSONDecodeError` before sending the request. Shows red error banner.  
**Status:** ✅ Handled in UI

---

## 5. Prompt Not Found in Registry
**Trigger:** User provides a `prompt_id` that does not exist.  
**Behaviour:** Registry returns `None`, service returns `error="Prompt not found"`.  
**Status:** ✅ Handled

---

## 6. Backend Offline (UI)
**Trigger:** FastAPI server not running when UI makes a request.  
**Behaviour:** Sidebar shows red `❌ API Offline` status. Button shows `ConnectionError` message.  
**Status:** ✅ Handled

---

## 7. Template Variable Missing
**Trigger:** Prompt template expects `{{ text }}` but variables dict is empty.  
**Behaviour:** Jinja2 renders the variable as empty string (silent). Potential improvement: strict mode.  
**Status:** ⚠️ Partial — no explicit warning raised yet

---

## 8. Schema Missing on Prompt
**Trigger:** Prompt registered without a `schema_def`.  
**Behaviour:** Generation skips validation and returns raw model text. No repair loop triggered.  
**Status:** ✅ Intentional — text-only prompts are valid

---

## 9. Contradictory Instructions
**Trigger:** Prompt says "return only JSON" but system message says "return plain text".  
**Behaviour:** Model may return plain text. Validation fails → repair loop triggered → resolved or fails gracefully.  
**Status:** ✅ Covered by repair loop

---

## 10. Cache Serving Stale Data
**Trigger:** Same prompt+variables called twice within 5 minutes.  
**Behaviour:** Second call returns cached result with `cached: true`. TTL is 300 seconds.  
**Status:** ✅ By design
