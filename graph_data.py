import json
from pathlib import Path
from typing import Optional, Union, Literal
from pydantic import BaseModel, Field, conint, confloat


# =======================================
# LARGE LANGUAGE MODEL CONFIGURATION
# =======================================

class AwsConfig(BaseModel):
    """
    Represents the AWS configuration needed for accessing AWS services.

    :param region: The AWS region (e.g., 'us-east-1').
    :param access_key: The AWS access key used for authentication.
    :param secret_key: The AWS secret key used for authentication.
    """

    region: str = Field(...,
                        description="The AWS region")

    access_key: str = Field(...,
                     description="The AWS access key")

    secret_key: str = Field(...,
                            description="The AWS secret key")

class LlmConfig(BaseModel):
    """
    Represents the configuration for a large language model.

    :param llm: The name of the large language model.
    :param version: The version of the large language model.
    :param host: The host server address where the model is deployed (ex. Ollama). Can be null if not applicable.
    :param api_key: The API key required for authentication (ex. OpenAi). Can be null if not applicable.
    :param aws_config: The AWS configuration for accessing additional resources. This field is optional.
    """

    llm: str = Field(...,
                     description="The name of the llm")

    version: str = Field(...,
                         description="The version of the llm")

    host: Optional[str] = Field(None,
                                description="The host server (can be null)")

    api_key: Optional[str] = Field(None,
                                   description="The API key for authentication (can be null)")

    aws_config: Optional[AwsConfig] = Field(None,
                                         description="AWS configuration")


# =======================================
# SYTEM PROMPT CONFIGURATION
# =======================================

class SystemPrompt(BaseModel):
    """
    The model ensures that exactly one of the following fields is provided:
    - `text`: A string containing the text content of the system prompt.
    - `path`: A string representing the file path of the system prompt.
    - `url`: A string for the URL of the markdown file containing the system prompt.

    :param text: Optional string containing the textual content of the system prompt.
    :param path: Optional string containing the file path of the system prompt.
    :param url: Optional string containing the URL of the markdown file with the system prompt.
    """

    text: Optional[str] = Field(None,
                                description="Text content of the system prompt")

    path: Optional[str] = Field(None,
                                description="Path of the system prompt file")

    url: Optional[str] = Field(None,
                               description="URL of the markdown file containing the system prompt")


# ============================
# NODE AGENT CONFIGURATION
# ============================

class PromptData(BaseModel):
    """
    Represents the system prompt configuration.

    :param system: The index of the system prompt
    :param placeholders: Key-value placeholders defined following the list
                         of values defined in the ke_prmpt as json file (node/node_name/node_name.json)
    """
    system: int = Field(
        ...,
        description="Index of the system prompt"
    )

    placeholders: dict[str, Union[str, float, int, bool, dict, list]] = Field(
        ...,
        description="Key-value dictionary of placeholders, "
    )


class NodeData(BaseModel):
    """
    Represents the configuration schema for an agent (node).

    :param id: Unique name of the agent
    :param llm: Index from LLM models list
    :param temperature: Controls randomness in LLM responses (0-1)
    :param show: Determines if output should be visible to the user
    :param prompt: Embedded object for the system prompt details
    """
    id: str = Field(
        ...,
        description="The unique name of the agent")

    llm: conint(ge=0) = Field(
        ...,
        description="The index from LLM models list")

    temperature: confloat(ge=0.0, le=1.0) = Field(
        ...,
        description="Parameter of the LLM, controlling randomness in responses")

    show: bool = Field(
        ...,
        description="Determines if the agent creates visible output for the user")

    prompt: PromptData = Field(
        ...,
        description="System prompt object")

# ======================
# EDGE DESCRIPTION
# ======================

class EdgeData(BaseModel):
    """
    Pydantic model representing an edge schema.

    :param source: Start edge node (id)
    :param target: End edge node (id)
    :param attrib: A specific node output, must be one of the allowed enum values
    """
    source: str = Field(...,
                        description="Start edge node (id)")

    target: str = Field(...,
                        description="End edge node (id)")
    
    attrib: Literal[
        "chat_messages",
        "user_message",
        "assistant_message",
        "history",
        "empty"
    ] = Field(
        ...,
        description="A possible string value representing a specific node output"
    )


# ======================
# GRAPH DESCRIPTION
# ======================

class GraphData(BaseModel):
    """
    A Pydantic model representing the Graph Configuration schema.

    # UTILS
    - Convert graph to json
      graph_.model_dump_json()

    - Initialize graph from json
      GraphData(**json_raw)


    :param models: Array containing configurations of large language models.
    :param systems: Array containing systems configurations.
    :param nodes: Array containing configurations of agents (graph nodes).
    :param edges: Array containing connections between graph nodes.
    :return:
    """

    models: list[LlmConfig] = Field(
        ...,
        description="Array containing configurations of large language models."
    )

    systems: list[SystemPrompt] = Field(
        ...,
        description="Array containing systems configurations"
    )

    nodes: list[NodeData] = Field(
        ...,
        description="Array containing configurations of agents (graph nodes)."
    )

    edges: list[EdgeData] = Field(
        ...,
        description="Array containing connections between graph nodes."
    )




