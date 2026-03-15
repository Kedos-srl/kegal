"""Shared prompt fixtures for LLM provider tests."""

from pathlib import Path
from kegal.llm.llm_model import LLMImageData, LLMStructuredOutput, LLMStructuredSchema, LLmMessage
from kegal.utils import load_images_to_base64

_ASSETS_DIR = Path(__file__).parent.parent.parent / "test" / "assets"


def get_chat_prompts() -> dict:
    return {
        "system_prompt": "You are a helpful assistant. Answer concisely.",
        "user_message": "What is 2 + 2? Reply with just the number.",
    }


def get_chat_prompt_with_history() -> dict:
    return {
        "system_prompt": "You are a helpful assistant.",
        "user_message": "What did I just tell you my name was?",
        "chat_history": [
            LLmMessage(role="user", content="My name is Alice."),
            LLmMessage(role="assistant", content="Nice to meet you, Alice!"),
        ],
    }


def get_image_prompts() -> dict:
    image_path = _ASSETS_DIR / "test_image.png"
    media_type, image_b64 = load_images_to_base64(str(image_path))
    return {
        "system_prompt": "You are a helpful assistant that describes images.",
        "user_message": "Describe what you see in this image in one sentence.",
        "images": [LLMImageData(media_type=media_type, image_b64=image_b64)],
    }


def get_pdf_prompts() -> dict:
    # PDF tests are skipped for providers that don't support it
    return {}


def get_tools_prompt() -> dict:
    from kegal.llm.llm_model import LLMTool, LLMStructuredSchema

    tool = LLMTool(
        name="get_weather",
        description="Get the current weather for a city",
        parameters={
            "city": LLMStructuredSchema(type="string", description="The city name"),
        },
        required=["city"],
    )
    return {
        "user_message": "What is the weather in Rome?",
        "tools": [tool],
    }


def get_structured_output_prompt() -> dict:
    schema = LLMStructuredOutput(
        json_output=LLMStructuredSchema(
            type="object",
            properties={
                "answer": {"type": "string", "description": "The direct answer"},
                "confidence": {"type": "number", "description": "Confidence 0-1"},
            },
            required=["answer", "confidence"],
        )
    )
    return {
        "system_prompt": "You are a helpful assistant. Always respond in the requested JSON format.",
        "user_messages": [
            "What is the capital of France?",
            "What is the capital of Germany?",
        ],
        "structured_output": schema,
    }
