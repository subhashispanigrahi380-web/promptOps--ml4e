from typing import Dict, Any, Tuple
import jsonschema
import json

class OutputValidator:
    @staticmethod
    def validate(content: Any, schema_def: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates the content against the JSON schema.
        Returns a tuple of (is_valid, error_message).
        """
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON string: {str(e)}"
                
        if not isinstance(content, dict):
            return False, "Response is not a valid JSON object."

        try:
            jsonschema.validate(instance=content, schema=schema_def)
            return True, ""
        except jsonschema.exceptions.ValidationError as e:
            return False, f"Schema validation error: {e.message}"
