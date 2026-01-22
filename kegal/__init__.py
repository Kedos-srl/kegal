"""
KeGAL - Kedos Graph Agent for LLM

A graph-based agent framework for LLMs that enables the development
of workflows structured as graphs.
"""

from .graph import (
    Graph,
    GraphModel,
    GraphInputData,
    NodePrompt,
    NodeMessagePassing,
    GraphNode,
    GraphEdge,
)
from .compiler import Compiler, CompiledOutput, CompiledNodeOutput
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

__version__ = "0.1.2"

__all__ = [
    # Graph models
    "Graph",
    "GraphModel",
    "GraphInputData",
    "NodePrompt",
    "NodeMessagePassing",
    "GraphNode",
    "GraphEdge",
    # Compiler
    "Compiler",
    "CompiledOutput",
    "CompiledNodeOutput",
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
