from pathlib import Path
from dotenv import load_dotenv

from .llm_openai import  LllmOpenai
from .llm_anthropic import LlmAnthropic
from .llm_bedrock import LlmBedrock
from .llm_ollama import LlmOllama

# os.getenv

TEST_DIR = Path(__file__).parent
load_dotenv(dotenv_path=TEST_DIR /  "aws.env")

class LlmHandler:
    _MODEL_MAPPING = {
        "anthropic_aws": LlmAnthropic,
        "ollama": LlmOllama,
        "anthropic": LlmAnthropic,
        "bedrock": LlmBedrock,
        "openai": LllmOpenai,  # Added missing OpenAI option
    }

    def __init__(self, **kwargs):

        if "llm" not in kwargs.keys():
            raise ValueError

        llm = kwargs.get("llm")

        model_class = self._MODEL_MAPPING.get(llm)
        if model_class is None:
            available_models = [k for k in self._MODEL_MAPPING.keys() if k is not None]
            raise ValueError(f"Unknown LLM model: {llm}. Available models: {available_models}")

        self.model = model_class(**kwargs)


    def complete(self, **kwargs):
        return self.model.complete(**kwargs)


