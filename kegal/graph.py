import yaml
import json

from pydantic import BaseModel, ConfigDict, model_validator
from pathlib import Path
from typing import Any, Literal

from .utils import load_contents
from .llm.llm_model import LLMTool


class GraphMcpServer(BaseModel):
    id: str
    transport: Literal["stdio", "sse"]
    # stdio transport
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # sse transport
    url: str | None = None


class GraphModel(BaseModel):
    llm: str
    model: str
    api_key: str | None = None
    host: str | None = None
    aws_region_name: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None

class GraphInputData(BaseModel):
    uri: str | None = None
    base64: str | None = None
    template: dict[str, Any] | None = None


class NodePrompt(BaseModel):
    template: int
    prompt_placeholders: dict[str, Any] | None = None
    user_message: bool | None = None
    retrieved_chunks: bool | None = None
    chat_history: str | None = None

class NodeMessagePassing(BaseModel):
    input: bool = False
    output: bool = False

class NodeBlackboard(BaseModel):
    read: bool = False
    write: bool = False

class GraphNode(BaseModel):
    id: str
    model: int
    temperature: float
    max_tokens: int
    show: bool
    message_passing: NodeMessagePassing = NodeMessagePassing()
    chat_history: str | None = None
    prompt: NodePrompt | None
    structured_output: dict[str, Any] | None = None
    react_output: dict[str, Any] | None = None
    react: NodeReact | None = None
    images: list[int] | None = None
    documents: list[int] | None = None
    tools: list[str] | None = None
    mcp_servers: list[str] | None = None
    blackboard: NodeBlackboard | None = None

class NodeReact(BaseModel):
    max_iterations: int = 10
    resume: bool = False
    resume_threshold: float = 0.8


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: str
    children: list["GraphEdge"] | None = None  # fan-out: sub-task decomposition
    fan_in: list["GraphEdge"] | None = None    # aggregation: wait for all listed nodes
    react: list["GraphEdge"] | None = None     # ReAct: available agent subgraphs

    @model_validator(mode="after")
    def _check_mutual_exclusivity(self) -> "GraphEdge":
        if self.react is not None and self.children is not None:
            raise ValueError(
                f"Edge for node '{self.node}': 'react' and 'children' are mutually exclusive"
            )
        return self

class Graph(BaseModel):
    models: list[GraphModel]
    images: list[GraphInputData] | None = None
    documents: list[GraphInputData] | None = None
    tools: list[LLMTool] | None = None
    mcp_servers: list[GraphMcpServer] | None = None
    prompts: list[GraphInputData]
    react_compact_prompts: list[GraphInputData] | None = None
    chat_history: dict[str, list[dict[str, str]]] | None = None
    user_message: str | None = None
    retrieved_chunks: str | None = None
    blackboard: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    # ---------- Serialization helpers ----------
    def to_yml(self) -> str:
        return yaml.dump(self.model_dump(), default_flow_style=False, sort_keys=False)

    def save_to_yml(self, file_path: str | Path) -> None:
        """Save the graph to a YAML file."""
        path = Path(file_path)
        path.write_text(self.to_yml(), encoding='utf-8')


    def to_json(self, exclude_none: bool = True) -> str:
        """Convert the graph to a JSON string."""
        return json.dumps(self.model_dump(exclude_none=exclude_none), indent=2, ensure_ascii=False)

    def save_to_json(self, file_path: str | Path, exclude_none: bool = True) -> None:
        """Save the graph to a JSON file."""
        json_content = self.to_json(exclude_none)
        path = Path(file_path)
        path.write_text(json_content, encoding='utf-8')


    @classmethod
    def from_uri(cls, uri: str):
        data = load_contents(uri)
        return cls(**data)

