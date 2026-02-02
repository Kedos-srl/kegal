import yaml
import json

from pydantic import BaseModel
from pathlib import Path
from typing import Any

from .utils import load_contents
from .llm.llm_model import LLMTool


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

class GraphNode(BaseModel):
    id: str
    model: int
    temperature: float
    max_tokens: int
    show: bool
    message_passing: NodeMessagePassing
    chat_history: str | None = None
    prompt: NodePrompt | None
    structured_output: dict[str, Any] | None = None
    images: list[int] | None = None
    documents: list[int] | None = None
    tools: list[int] | None = None

class GraphEdge(BaseModel):
    node: str
    children: list[str] | None = None

class Graph(BaseModel):
    models: list[GraphModel]
    images: list[GraphInputData] | None = None
    documents: list[GraphInputData] | None = None
    tools: list[LLMTool] | None = None
    prompts: list[GraphInputData]
    chat_history: dict[str, list[dict[str, str]]] | None = None
    user_message: str | None = None
    retrieved_chunks: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    # ---------- Serialization helpers ----------
    def to_yml(self, exclude_none: bool = True) -> str:
        #graph_dict = self.model_dump(exclude_none=True)
        # Convert to YAML string
        return yaml.dump(self.model_dump(), default_flow_style=False, sort_keys=False)

    def save_to_yml(self, file_path: str | Path, exclude_none: bool = True) -> None:
        """Save the graph to a YAML file."""
        yaml_content = self.to_yml(exclude_none)
        path = Path(file_path)
        path.write_text(yaml_content, encoding='utf-8')


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

