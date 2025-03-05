from pydantic import BaseModel, Field

from tools_manager import ToolsManager, ToolConfig


class LlmResponse(BaseModel):
    """
    Represents a response from a large language model (LLM).

    :param response_content: contains the LLM's response structured according to the format
                             specified in the prompt OUTPUT step.
    :param prompt_size: The size (number of tokens or characters) of the input prompt.
    :param response_size: The size (number of tokens or characters) of the LLM's response.
    """
    id: str = Field(..., description="A unique identifier for the response.")
    message_content: str = Field(..., description="The content of the input message.")
    response_content: dict = Field(..., description="The content of the response generated by the LLM.")
    prompt_size: int = Field(..., description="The size (number of tokens or characters) of the input prompt.")
    response_size: int = Field(..., description="The size (number of tokens or characters) of the LLM's response.")


def validate_llm_response(response_: LlmResponse) -> bool:
    if "validation" in response_.response_content:
        return response_.response_content["validation"]
    else:
        raise ValueError("Invalid response format")

def stringify_tool_result(value):
    """
    Convert any non-string value to a string.
    If the value is already a string, return it unchanged.
    """
    if isinstance(value, str):
        return value
    else:
        return str(value)


def get_response_message(response_: LlmResponse) -> str:
    if "response_txt" in response_.response_content:
        return response_.response_content["response_txt"]
    elif "response_obj" in response_.response_content:
        return response_.response_content["response_obj"]
    elif "response_tool" in response_.response_content:
        response_tool = response_.response_content["response_tool"]
        config = ToolConfig(**response_tool)
        manager = ToolsManager()
        result = manager.execute_from_config(config)
        return stringify_tool_result(result)
    else:
        return ""
