from pydantic import BaseModel, field_validator
from typing import Any

from .graph_react import NodeReact
from .graph_blackboard import NodeBlackboardRef


class NodePrompt(BaseModel):
    template: int
    prompt_placeholders: dict[str, Any] | None = None
    user_message: bool | None = None
    retrieved_chunks: bool | None = None
    chat_history: str | None = None
    batch_use_messages: list[int] | None = None


class NodeMessagePassing(BaseModel):
    input: bool = False
    output: bool = False


class NodeBatchMessagePassing(BaseModel):
    input: bool = False
    output: bool = False


class NodeMcpServerRef(BaseModel):
    id: str
    tools: list[str] | None = None

    @field_validator('tools')
    @classmethod
    def _check_tools(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError(
                "'tools' must be None (expose all tools) or a non-empty list of tool names; "
                "an empty list disables all tools from this server"
            )
        return v


class GraphNode(BaseModel):
    id: str
    model: int
    temperature: float
    max_tokens: int
    show: bool
    message_passing: NodeMessagePassing = NodeMessagePassing()
    batch_message_passing: NodeBatchMessagePassing | None = None
    prompt: NodePrompt | None
    structured_output: dict[str, Any] | None = None
    react_output: dict[str, Any] | None = None
    react: NodeReact | None = None
    max_tool_calls: int | None = None
    images: list[int] | None = None
    documents: list[int] | None = None
    tools: list[str] | None = None
    mcp_servers: list[NodeMcpServerRef] | None = None
    blackboard: NodeBlackboardRef | None = None

    @field_validator('mcp_servers', mode='before')
    @classmethod
    def _normalize_mcp_servers(cls, v):
        if v is None:
            return None
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({'id': item})
            elif isinstance(item, (dict, NodeMcpServerRef)):
                result.append(item)
            else:
                raise ValueError(
                    f"mcp_servers items must be a server ID string or an object with 'id', "
                    f"got {type(item).__name__}"
                )
        return result
