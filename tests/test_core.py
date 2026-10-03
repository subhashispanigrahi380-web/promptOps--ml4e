import pytest
import os
from app.services.registry import PromptRegistry
from app.services.validator import OutputValidator

def test_registry_add_and_get():
    # Use in-memory or temp db for test
    registry = PromptRegistry(db_path=":memory:")
    
    schema = {"type": "object", "properties": {"key": {"type": "string"}}}
    prompt_def = registry.add_prompt("test_prompt", "Hello {{ name }}", schema_def=schema)
    
    assert prompt_def.name == "test_prompt"
    assert prompt_def.version == 1
    assert prompt_def.schema_def == schema
    
    # Retrieve
    retrieved = registry.get_prompt("test_prompt")
    assert retrieved.id == "test_prompt_v1"
    assert retrieved.template == "Hello {{ name }}"

def test_output_validator_valid():
    schema = {
        "type": "object", 
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
    }
    
    is_valid, err = OutputValidator.validate({"name": "Alice"}, schema)
    assert is_valid
    assert err == ""

def test_output_validator_invalid_schema():
    schema = {
        "type": "object", 
        "properties": {"name": {"type": "string"}},
        "required": ["name"]
    }
    
    is_valid, err = OutputValidator.validate({"age": 30}, schema)
    assert not is_valid
    assert "name" in err or "required" in err

def test_output_validator_invalid_json_string():
    schema = {"type": "object"}
    is_valid, err = OutputValidator.validate("{bad json", schema)
    assert not is_valid
    assert "Invalid JSON" in err
