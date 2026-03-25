import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from .compose import compose_template_prompt, compose_node_prompt, compose_images, compose_documents, compose_tools
from .graph import Graph, GraphNode
from .utils import load_contents
from .llm.llm_handler import LlmHandler
from .llm.llm_model import LLmResponse, LLMStructuredOutput, LLMStructuredSchema

import logging

logger = logging.getLogger(__name__)


class CompiledNodeOutput(BaseModel):
    node_id: str
    response: LLmResponse
    compiled_time: float
    show: bool
    history: bool

class CompiledOutput(BaseModel):
    nodes: list[CompiledNodeOutput] = []
    input_size: int = 0
    output_size: int = 0
    compile_time: float = 0


class Compiler:
    def __init__(self, uri: str | None = None,
                       source: dict | None = None) -> None:
        if uri is not None:
            graph = Graph.from_uri(uri)
        else:
            graph = Graph.model_validate(source)

        self.clients: list[LlmHandler] = [LlmHandler(**model.model_dump(exclude_none=True)) for model in graph.models]
        self.images = graph.images
        self.documents = graph.documents
        self.tools = graph.tools
        self.prompts = self._get_graph_prompts_templates(graph)
        self.chat_history = graph.chat_history
        self.user_message = graph.user_message
        self.retrieved_chunks = graph.retrieved_chunks
        self.outputs: CompiledOutput = CompiledOutput()
        self.message_passing: list[Any] = []
        self.nodes = {node.id: node for node in graph.nodes}
        self.edges = graph.edges

    @staticmethod
    def _get_graph_prompts_templates(graph):
        prompts_templates: list[dict[str, str]] = []
        for prompt_input in graph.prompts:
            if prompt_input.template is not None:
                prompts_templates.append(compose_template_prompt(prompt_input.template))
            elif prompt_input.uri is not None:
                prompts_templates.append(
                    compose_template_prompt(
                        load_contents(prompt_input.uri)
                    )
                )
            else:
                raise ValueError("Prompt input must have either 'template' or 'uri' defined")
        return prompts_templates

    # -------------------------------------------------------------------------
    # DAG building
    # -------------------------------------------------------------------------

    def _build_dag(self) -> dict[str, set[str]]:
        """Return a dependency map: node_id → set of node_ids that must finish first.

        Dependencies are resolved in this priority order:
        1. Explicit ``depends_on`` on the edge.
        2. Inferred from ``message_passing``: any node with ``output:true``
           is a dependency of any node with ``input:true`` that appears later
           in the edge list.
        3. Guard nodes (structured_output contains ``validation``) implicitly
           precede every non-guard node.
        """
        deps: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}

        # Collect all node ids in edge order (parent first, then children)
        ordered_ids: list[str] = []
        for edge in self.edges:
            if edge.node not in ordered_ids:
                ordered_ids.append(edge.node)
            if edge.children:
                for child in edge.children:
                    if child not in ordered_ids:
                        ordered_ids.append(child)

        # 1. Explicit depends_on
        for edge in self.edges:
            if edge.depends_on:
                for dep in edge.depends_on:
                    deps[edge.node].add(dep)
            if edge.children and edge.depends_on:
                for child in edge.children:
                    for dep in edge.depends_on:
                        deps[child].add(dep)

        # 2. message_passing inference: output node → all subsequent input nodes
        output_nodes = [
            nid for nid in ordered_ids
            if self.nodes[nid].message_passing.output
        ]
        input_nodes = [
            nid for nid in ordered_ids
            if self.nodes[nid].message_passing.input
        ]
        for out_nid in output_nodes:
            out_idx = ordered_ids.index(out_nid)
            for in_nid in input_nodes:
                in_idx = ordered_ids.index(in_nid)
                if in_idx > out_idx:
                    deps[in_nid].add(out_nid)

        # 3. Guard nodes precede all non-guard nodes
        guard_ids = [
            nid for nid in ordered_ids
            if self._is_guard_node(self.nodes[nid])
        ]
        non_guard_ids = [nid for nid in ordered_ids if nid not in guard_ids]
        for nid in non_guard_ids:
            for gid in guard_ids:
                deps[nid].add(gid)

        return deps

    @staticmethod
    def _is_guard_node(node: GraphNode) -> bool:
        if node.structured_output is None:
            return False
        so = node.structured_output
        # Support both 'parameters' (kegal schema style) and 'properties' (JSON Schema style)
        fields = so.get("parameters") or so.get("properties") or {}
        return "validation" in fields

    def _topological_levels(self, deps: dict[str, set[str]]) -> list[list[str]]:
        """Kahn's algorithm — returns nodes grouped into levels.
        Nodes in the same level have no dependency on each other and can run
        in parallel.
        """
        remaining = {nid: set(d) for nid, d in deps.items()}
        levels: list[list[str]] = []

        while remaining:
            # nodes whose dependencies are all resolved
            ready = [nid for nid, d in remaining.items() if not d]
            if not ready:
                cycle = list(remaining.keys())
                raise ValueError(f"Cycle detected in graph among nodes: {cycle}")
            levels.append(sorted(ready))  # sorted for deterministic order
            for nid in ready:
                del remaining[nid]
            for d in remaining.values():
                d -= set(ready)

        return levels

    # -------------------------------------------------------------------------
    # Compile entry point
    # -------------------------------------------------------------------------

    def compile(self):
        global_start = time.time()
        deps = self._build_dag()
        levels = self._topological_levels(deps)

        logger.debug(f"DAG levels: {levels}")

        for level in levels:
            guard_ids   = [nid for nid in level if self._is_guard_node(self.nodes[nid])]
            regular_ids = [nid for nid in level if nid not in guard_ids]

            # Phase 1 — run guard nodes sequentially first
            for nid in guard_ids:
                passed = self._run_node(self.nodes[nid])
                if passed is False:
                    logger.info(f"Guard node '{nid}' blocked execution — aborting.")
                    self.outputs.compile_time = time.time() - global_start
                    return

            # Phase 2 — run regular nodes; parallel if >1, sequential if 1
            if len(regular_ids) > 1:
                self._run_parallel(regular_ids)
            elif len(regular_ids) == 1:
                self._run_node(self.nodes[regular_ids[0]])

        self.outputs.compile_time = time.time() - global_start

    def _run_parallel(self, node_ids: list[str]):
        """Execute independent nodes concurrently using a thread pool."""
        with ThreadPoolExecutor(max_workers=len(node_ids)) as executor:
            futures = {
                executor.submit(self._run_node, self.nodes[nid]): nid
                for nid in node_ids
            }
            for future in as_completed(futures):
                nid = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.exception(f"Node '{nid}' failed during parallel execution: {e}")

    # -------------------------------------------------------------------------
    # Single-node execution
    # -------------------------------------------------------------------------

    def _run_node(self, node: GraphNode) -> bool:
        """Execute a single node. Returns False if a validation gate fails or a guard node errors."""
        if node.prompt is None:
            return True
        is_guard = self._is_guard_node(node)
        try:
            start = time.time()
            model_body = self._build_model_body(node)
            enable_history = "chat_history" in model_body
            response: LLmResponse = self.clients[node.model].complete(**model_body)
            elapsed = time.time() - start
            logger.debug(f"Node '{node.id}' completed in {elapsed:.3f}s")
            self._record_output(node, response, elapsed, enable_history)
            self._check_message_passing(response, node)
            return self._check_validation_gate(response)
        except Exception as e:
            logger.exception(f"Failed to execute node '{node.id}': {e}")
            # if it's not a guard node, we re-raise the exception to fail fast and avoid running dependent nodes with potentially inconsistent state
            if not is_guard :
                raise e
            # Guard node errors are treated as a failed validation — abort the graph
            return not is_guard

    # -------------------------------------------------------------------------
    # Node body helpers
    # -------------------------------------------------------------------------

    def _chat_history_check(self, node) -> bool:
        if node.prompt is None or node.prompt.chat_history is None or self.chat_history is None:
            return False
        return node.prompt.chat_history in self.chat_history

    def _images_check(self, node) -> bool:
        if node.images is None or self.images is None:
            return False
        return True

    def _documents_check(self, node) -> bool:
        if node.documents is None or self.documents is None:
            return False
        return True

    def _tools_check(self, node) -> bool:
        if node.tools is None or self.tools is None:
            return False
        return True

    def _compose_node_prompt(self, node):
        prompt_elements: dict[str, Any] = {
            "prompt_template": self.prompts[node.prompt.template]
        }

        if node.prompt.prompt_placeholders:
            prompt_elements["placeholders"] = node.prompt.prompt_placeholders
        else:
            prompt_elements["placeholders"] = {}

        if node.prompt.user_message:
            prompt_elements["user_message"] = self.user_message

        if node.message_passing.input:
            prompt_elements["message_passing"] = self.message_passing

        if node.prompt.retrieved_chunks:
            prompt_elements["retrieved_chunks"] = self.retrieved_chunks

        return compose_node_prompt(**prompt_elements)

    def _build_model_body(self, node) -> dict[str, Any]:
        body: dict[str, Any] = {
            "temperature": node.temperature,
            "max_tokens": node.max_tokens,
        }

        composed_prompt = self._compose_node_prompt(node)
        if composed_prompt["system"] != "":
            body["system_prompt"] = composed_prompt["system"]
        if composed_prompt["user"] != "":
            body["user_message"] = composed_prompt["user"]

        if self._chat_history_check(node):
            body["chat_history"] = self.chat_history[node.prompt.chat_history]

        if self._images_check(node):
            body["imgs_b64"] = compose_images(self.images, node.images)

        if self._documents_check(node):
            body["pdfs_b64"] = compose_documents(self.documents, node.documents)

        if self._tools_check(node):
            body["tools_data"] = compose_tools(self.tools, node.tools)

        if node.structured_output is not None:
            body["structured_output"] = LLMStructuredOutput(
                json_output=LLMStructuredSchema(**node.structured_output)
            )

        return body

    def _record_output(self, node, response: LLmResponse, compiled_time: float, enable_history: bool) -> None:
        self.outputs.nodes.append(
            CompiledNodeOutput(
                node_id=node.id,
                response=response,
                compiled_time=compiled_time,
                show=node.show,
                history=enable_history,
            )
        )
        self.outputs.input_size += response.input_size
        self.outputs.output_size += response.output_size

    def _check_message_passing(self, response, node):
        if not node.message_passing.input and not node.message_passing.output:
            self.message_passing.clear()
            return
        if node.message_passing.output:
            if response.messages is not None and len(response.messages) > 0:
                self.message_passing.extend(response.messages)
            elif response.json_output is not None:
                self.message_passing.append(response.json_output)

    @staticmethod
    def _check_validation_gate(response: LLmResponse) -> bool:
        if response.json_output is not None and "validation" in response.json_output:
            return bool(response.json_output["validation"])
        return True

    # -------------------------------------------------------------------------
    # Output helpers
    # -------------------------------------------------------------------------

    def get_outputs(self) -> CompiledOutput:
        return self.outputs

    def get_outputs_json(self, indent: int) -> str:
        return json.dumps(self.outputs.model_dump(), indent=indent)

    def save_outputs_as_json(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.outputs.model_dump(), f, indent=4)

    def save_outputs_as_markdown(self, path: Path, only_content: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if only_content:
            md = ""
            for i, output in enumerate(self.outputs.nodes):
                if output.response.messages:
                    for message in output.response.messages:
                        md += message
                if i > 0:
                    md += "\n"
                    md += "---"
        else:
            md = "## Graph Response\n"
            md += f" * Token Input size: {self.outputs.input_size}\n"
            md += f" * Token Output size: {self.outputs.output_size}\n"
            md += f" * Compile time: {self.outputs.compile_time}\n"
            for output in self.outputs.nodes:
                md += f"### Node:  {output.node_id}\n"
                if output.response.json_output is not None:
                    md += f"""```json\n {json.dumps(output.response.json_output, indent=4)} \n```\n"""
                if output.response.tools is not None:
                    md += f"""```json\n {json.dumps(output.response.tools, indent=4)} \n```\n"""
                md += f"\nToken Input size:  {output.response.input_size} \n "
                md += f" Token Output size:  {output.response.output_size} \n "

        with open(path, "w") as f:
            f.write(md)
