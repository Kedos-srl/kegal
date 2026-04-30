import yaml
import json

from pydantic import BaseModel, model_validator
from pathlib import Path
from typing import Any

from .utils import load_contents
from .llm.llm_model import LLMTool

# Sub-module imports (also re-exported for backward compatibility)
from .graph_mcp import GraphMcpServer
from .graph_model import GraphModel
from .graph_react import NodeReact
from .graph_edge import GraphEdge
from .graph_blackboard import GraphBlackboard, BlackboardEntry, NodeBlackboardRef
from .graph_node import NodePrompt, NodeMessagePassing, GraphNode


class GraphInputData(BaseModel):
    uri: str | None = None
    base64: str | None = None
    template: dict[str, Any] | None = None


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
    blackboard: GraphBlackboard | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def _validate_node_ids(self) -> "Graph":
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"Duplicate node id: '{node.id}'")
            seen.add(node.id)
        return self

    # ---------- Serialization helpers ----------

    def to_yml(self) -> str:
        return yaml.dump(self.model_dump(), default_flow_style=False, sort_keys=False)

    def save_to_yml(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.write_text(self.to_yml(), encoding='utf-8')

    def to_json(self, exclude_none: bool = True) -> str:
        return json.dumps(self.model_dump(exclude_none=exclude_none), indent=2, ensure_ascii=False)

    def save_to_json(self, file_path: str | Path, exclude_none: bool = True) -> None:
        json_content = self.to_json(exclude_none)
        path = Path(file_path)
        path.write_text(json_content, encoding='utf-8')

    @classmethod
    def from_uri(cls, uri: str):
        data = load_contents(uri)
        return cls(**data)


__all__ = [
    "GraphMcpServer",
    "GraphModel",
    "NodeReact",
    "GraphEdge",
    "GraphBlackboard",
    "BlackboardEntry",
    "NodeBlackboardRef",
    "NodePrompt",
    "NodeMessagePassing",
    "GraphNode",
    "GraphInputData",
    "Graph",
]
