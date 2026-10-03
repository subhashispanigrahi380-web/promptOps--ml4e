from app.services.llm_base import LLMProvider
from app.services.mock_llm import MockLLM
from app.services.litellm_provider import LiteLLMProvider

class ModelRouter:
    def __init__(self):
        self.providers = {
            "mock": MockLLM(),
            "fast": LiteLLMProvider(default_model="gpt-3.5-turbo"),
            "quality": LiteLLMProvider(default_model="gpt-4o")
        }

    def route(self, task_type: str) -> LLMProvider:
        """
        Simple routing rule based on task type.
        """
        if task_type == "extraction":
            return self.providers["fast"]
        elif task_type == "complex_reasoning":
            return self.providers["quality"]
        else:
            # Fallback or testing
            return self.providers["mock"]
