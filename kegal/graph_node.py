from pydantic import BaseModel
from typing import Any

from .graph_react import NodeReact
from .graph_blackboard import NodeBlackboardRef


class NodePrompt(BaseModel):
    template: int
    prompt_placeholders: dict[str, Any] | None = None
    user_message: bool | None = None
    retrieved_chunks: bool | None = None
    chat_history: str | None = None


class NodeMessagePassing(BaseModel):
    input: bool = False
    output: bool = False


class GraphNode(BaseModel):
    id: str
    model: int
    temperature: float
    max_tokens: int
    show: bool
    message_passing: NodeMessagePassing = NodeMessagePassing()
    prompt: NodePrompt | None
    structured_output: dict[str, Any] | None = None
    react_output: dict[str, Any] | None = None
    react: NodeReact | None = None
    images: list[int] | None = None
    documents: list[int] | None = None
    tools: list[str] | None = None
    mcp_servers: list[str] | None = None
    blackboard: NodeBlackboardRef | None = None
