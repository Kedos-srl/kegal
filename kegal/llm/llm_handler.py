from typing import Any

from .llm_model import LLmResponse
from .llm_openai import LlmOpenai
from .llm_anthropic import LlmAnthropic
from .llm_bedrock import LlmBedrock
from .llm_ollama import LlmOllama


class LlmHandler:
    _MODEL_MAPPING = {
        "anthropic_aws": LlmAnthropic,
        "ollama": LlmOllama,
        "anthropic": LlmAnthropic,
        "bedrock": LlmBedrock,
        "openai": LlmOpenai,
    }

    def __init__(self, **kwargs):

        if "llm" not in kwargs.keys():
            raise ValueError("Missing required parameter: 'llm'")

        llm = kwargs.get("llm")

        model_class = self._MODEL_MAPPING.get(llm)
        if model_class is None:
            available_models = list(self._MODEL_MAPPING.keys())
            raise ValueError(f"Unknown LLM model: {llm}. Available models: {available_models}")

        self.model = model_class(**kwargs)


    def complete(self, **kwargs: Any) -> LLmResponse:
        return self.model.complete(**kwargs)


