"""
KeGAL - Kedos Graph Agent for LLM

A graph-based agent framework for LLMs that enables the development
of workflows structured as graphs.
"""

from .graph import (
    Graph,
    GraphModel,
    GraphInputData,
    GraphBlackboard,
    BlackboardEntry,
    NodeBlackboardRef,
    ChatHistoryFile,
    NodePrompt,
    NodeMessagePassing,
    NodeReact,
    GraphNode,
    GraphEdge,
    GraphMcpServer,
)
from .compiler import Compiler, CompiledOutput, CompiledNodeOutput, ReactTrace, ReactIteration
from .compose import (
    compose_template_prompt,
    compose_node_prompt,
    compose_images,
    compose_documents,
    compose_tools,
)
from .utils import (
    load_yml,
    load_json,
    load_contents,
    load_images_to_base64,
    load_pdfs_to_base64,
)
from .validators import (
    validate_anthropic_schema,
    validate_openai_schema,
    validate_llm_input_schema,
    SchemaIssue,
)

# Import LLM subpackage
from . import llm

__version__ = "0.1.2.4"

__all__ = [
    # Graph models
    "Graph",
    "GraphModel",
    "GraphInputData",
    "GraphBlackboard",
    "BlackboardEntry",
    "NodeBlackboardRef",
    "ChatHistoryFile",
    "NodePrompt",
    "NodeMessagePassing",
    "NodeReact",
    "GraphNode",
    "GraphEdge",
    "GraphMcpServer",
    # Compiler
    "Compiler",
    "CompiledOutput",
    "CompiledNodeOutput",
    "ReactTrace",
    "ReactIteration",
    # Compose utilities
    "compose_template_prompt",
    "compose_node_prompt",
    "compose_images",
    "compose_documents",
    "compose_tools",
    # Utils
    "load_yml",
    "load_json",
    "load_contents",
    "load_images_to_base64",
    "load_pdfs_to_base64",
    # Validators
    "validate_anthropic_schema",
    "validate_openai_schema",
    "validate_llm_input_schema",
    "SchemaIssue",
    # LLM subpackage
    "llm",
]
