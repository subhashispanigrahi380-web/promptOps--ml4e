from typing import Dict, Any, Tuple, Optional
import jsonschema
import json
from pydantic import BaseModel, ValidationError

class OutputValidator:
    @staticmethod
    def validate(content: Any, schema_def: Optional[Dict[str, Any]] = None, pydantic_cls: Optional[type] = None) -> Tuple[bool, str]:
        """
        Validates content against JSON Schema or Pydantic model.
        Returns:
            (is_valid: bool, error_message: str)
        """
        # 1. Parse JSON if passed as string
        if isinstance(content, str):
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                content = json.loads(cleaned)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON string: {str(e)}"

        if not isinstance(content, dict):
            return False, "Response is not a valid JSON object."

        # 2. Pydantic validation if model provided
        if pydantic_cls and issubclass(pydantic_cls, BaseModel):
            try:
                pydantic_cls.model_validate(content)
                return True, ""
            except ValidationError as e:
                errors = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
                return False, f"Pydantic Validation Error: {'; '.join(errors)}"

        # 3. JSON Schema validation
        if schema_def:
            try:
                jsonschema.validate(instance=content, schema=schema_def)
                return True, ""
            except jsonschema.exceptions.ValidationError as e:
                path = " -> ".join([str(p) for p in e.path]) if e.path else "root"
                return False, f"Schema validation error at [{path}]: {e.message}"
            except Exception as e:
                return False, f"Schema validation exception: {str(e)}"

        return True, ""
