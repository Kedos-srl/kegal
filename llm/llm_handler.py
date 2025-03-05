from PIL import Image

from ke_llm.llm.llm_response import LlmResponse
from abc import ABC, abstractmethod
import json
import re
import json_repair


class LlmHandler(ABC):
    """
    Abstract Base Class for a node that interacts with a Large Language Model (LLM).
    """

    @abstractmethod
    def complete(self, prompt_: str, temperature_: float = 0.5) -> dict:
        """
        Generates a completion for the provided prompt based on LLM processing.

        :param prompt_: The input prompt string for the LLM to process.
        :param temperature_: A float controlling the randomness of the completion:
                             - Higher values (e.g., 0.8) create more random responses.
                             - Lower values (e.g., 0.2) generate more focused responses. Default is 0.5.

        :return: response_content, prompt_size, response_size
        """
        pass

    @abstractmethod
    def interpret(self, prompt_: str, image_: Image, max_size: int,  temperature_: float = 0.0) -> dict:
        """
        Generates an interpretation of an image based on the provided prompt.

        :param prompt_: The input prompt string for the LLM to process.
        :param temperature_: A float controlling the randomness of the completion:
                             - Higher values (e.g., 0.8) create more random responses.
                             - Lower values (e.g., 0.2) generate more focused responses. Default is 0.5.

        :return: response_content, prompt_size, response_size
        """
        pass

    @staticmethod
    def _cleanup_json_string(json_string) -> dict:
        """
            Cleans up a JSON string by removing enclosing markdown-style fences or simple triple backticks
            and validates its JSON format before returning it.

            :param json_string: The input JSON string with potential markdown fences or triple backticks.
            :return: A dictionary parsed from the JSON string.

            :raises ValueError: If the cleaned string is not a valid JSON.
            """
        if not json_string:
            raise ValueError("Empty JSON string provided")

            # Pattern to match markdown-style fences like ```json...``` and simple backticks like ```...```
        pattern = r'```(?:json)?\s*(.*?)\s*```'
        matches = re.findall(pattern, json_string, re.DOTALL)

        if matches:
            cleaned_string = matches[0].strip()
        else:
            cleaned_string = json_string.strip()

        # Remove any additional whitespace and normalize newlines
        cleaned_string = re.sub(r'\s+', ' ', cleaned_string)

        # # Add closing brace if missing
        if not cleaned_string.rstrip().endswith('}'):
            cleaned_string = cleaned_string.rstrip() + '}'

        try:
            # Rest of the function remains the same...
            out = json_repair.loads(cleaned_string.encode('utf-8').decode())
            return out

        except json.JSONDecodeError as e:
            print("Problematic JSON string:")
            print(cleaned_string)
            raise ValueError(f"Invalid JSON format at position {e.pos}: {e.msg}") from e