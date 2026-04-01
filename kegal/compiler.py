import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel
from .compose import compose_template_prompt, compose_node_prompt, compose_images, compose_documents, compose_tools
from .graph import Graph, GraphEdge, GraphNode
from .mcp_handler import McpHandler
from .utils import load_contents
from .llm.llm_handler import LlmHandler
from .llm.llm_model import LLmResponse, LLMStructuredOutput, LLMStructuredSchema, LLmMessage

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
                       source: dict | None = None,
                       tool_executors: dict[str, Callable] | None = None) -> None:
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
        self.graph_mcp_servers = graph.mcp_servers or []

        # Static tool executors: name → Python callable
        self.tool_executors: dict[str, Callable] = tool_executors or {}

        # MCP handlers: server id → McpHandler (connected at init)
        self.mcp_handlers: dict[str, McpHandler] = {}
        for server_cfg in self.graph_mcp_servers:
            handler = McpHandler(server_cfg)
            try:
                handler.connect()
                self.mcp_handlers[server_cfg.id] = handler
            except Exception as e:
                logger.error(f"Failed to connect MCP server '{server_cfg.id}': {e}")

    def close(self) -> None:
        """Release all resources held by this compiler.

        - MCP servers: stopped only if any were connected.
        - LLM clients: closed only if the underlying provider exposes close().
        - Tool executors: plain callables, nothing to release.
        Safe to call more than once.
        """
        if self.mcp_handlers:
            for server_id, handler in self.mcp_handlers.items():
                try:
                    handler.disconnect()
                except Exception as e:
                    logger.warning(f"Error closing MCP server '{server_id}': {e}")
            self.mcp_handlers.clear()

        for client in self.clients:
            if hasattr(client.model, "close"):
                try:
                    client.model.close()
                except Exception as e:
                    logger.warning(f"Error closing LLM client: {e}")

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

        Dependencies are resolved in three stages:
        1. Explicit structural dependencies from the recursive edge tree:
           - ``children``: fan-out — each child depends on its parent node.
           - ``fan_in``: aggregation — the node depends on every node listed.
        2. Inferred from ``message_passing``: any node with ``output:true``
           is a dependency of any node with ``input:true`` that appears later
           in the collected node order.
        3. Guard nodes (structured_output contains ``validation``) implicitly
           precede every non-guard node.

        Known limitation: ``detect_cycles`` catches cycles within a single
        recursive edge declaration but not cross-root cycles (e.g. root A has
        child B, root B has child A). Cross-root cycles are caught downstream
        by ``_topological_levels`` via Kahn's algorithm.
        """
        deps: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        declared_structure: dict[str, GraphEdge] = {}

        # — Cycle detection ————————————————————————————————————————————————
        def detect_cycles(edge: GraphEdge, path: set[str]) -> None:
            if edge.node in path:
                raise ValueError(
                    f"Cycle detected in edges involving node '{edge.node}'"
                )
            path = path | {edge.node}
            for child in (edge.children or []):
                detect_cycles(child, path)
            for fi in (edge.fan_in or []):
                detect_cycles(fi, path)

        # — Recursive traversal ————————————————————————————————————————————
        def traverse(edge: GraphEdge) -> None:
            node_id = edge.node

            if node_id not in self.nodes:
                raise ValueError(
                    f"Edge references unknown node '{node_id}'"
                )

            # Warn on contradictory internal structure for the same node id
            has_structure = edge.children is not None or edge.fan_in is not None
            if has_structure:
                if node_id in declared_structure:
                    prev = declared_structure[node_id]
                    if prev.children != edge.children or prev.fan_in != edge.fan_in:
                        logger.warning(
                            f"Node '{node_id}' has contradictory structure declarations. "
                            f"First declaration is canonical; subsequent ones are ignored."
                        )
                else:
                    declared_structure[node_id] = edge

            # fan_in: node_id depends on every node listed in fan_in
            for fi_edge in (edge.fan_in or []):
                traverse(fi_edge)               # validate before accessing deps
                deps[node_id].add(fi_edge.node)

            # children: every child depends on node_id
            for child_edge in (edge.children or []):
                traverse(child_edge)             # validate before accessing deps
                deps[child_edge.node].add(node_id)

        # — Stage 1: explicit dependencies from edge tree ——————————————————
        for root_edge in self.edges:
            detect_cycles(root_edge, set())
            traverse(root_edge)

        # — Stage 2: message_passing inference (unchanged) ————————————————
        # Collect node order via DFS pre-order traversal of the edge tree.
        # Nodes not referenced in any edge are appended in declaration order.
        ordered_ids: list[str] = []

        def collect_ids(e: GraphEdge) -> None:
            if e.node not in ordered_ids:
                ordered_ids.append(e.node)
            for child in (e.children or []):
                collect_ids(child)
            for fi in (e.fan_in or []):
                collect_ids(fi)

        for edge in self.edges:
            collect_ids(edge)

        for node_id in self.nodes:
            if node_id not in ordered_ids:
                ordered_ids.append(node_id)

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

        # — Stage 3: guard nodes precede all non-guard nodes (unchanged) ———
        guard_ids = [nid for nid, n in self.nodes.items() if self._is_guard_node(n)]
        non_guard_ids = [nid for nid in self.nodes if nid not in guard_ids]
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

        # Warn when concurrent output:true nodes share a topological level.
        # Their writes to self.message_passing will be non-deterministically
        # interleaved; a downstream input:true node will receive arbitrary output.
        for level in levels:
            output_in_level = [
                nid for nid in level
                if self.nodes[nid].message_passing.output
            ]
            if len(output_in_level) > 1:
                logger.warning(
                    f"Nodes {output_in_level} are at the same execution level "
                    f"and all have message_passing.output=true. Their outputs will be "
                    f"written to self.message_passing concurrently in non-deterministic "
                    f"order. Consider restructuring to avoid concurrent writes to the "
                    f"message pipe."
                )

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
        """Execute a single node including the tool loop. Returns False if a validation gate fails."""
        if node.prompt is None:
            return True
        is_guard = self._is_guard_node(node)
        try:
            start = time.time()
            model_body = self._build_model_body(node)
            enable_history = "chat_history" in model_body

            response = self._run_tool_loop(node, model_body)

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

    def _run_tool_loop(self, node: GraphNode, model_body: dict[str, Any]) -> LLmResponse:
        """Call the LLM and execute tool calls until the model returns a final answer."""
        client = self.clients[node.model]
        # Keep a mutable copy so we can inject tool results into history
        body = dict(model_body)
        tool_history: list[LLmMessage] = list(body.get("chat_history") or [])

        original_user_message = body.get("user_message", "")
        accumulated_tool_results: list[str] = []

        MAX_ITERATIONS = 10
        for iteration in range(MAX_ITERATIONS):
            if tool_history:
                body["chat_history"] = tool_history

            response: LLmResponse = client.complete(**body)

            # No tool calls → final answer
            if not response.tools:
                if accumulated_tool_results:
                    response.tool_results = accumulated_tool_results
                return response

            # On first tool call: move the user message into history so it isn't
            # duplicated on subsequent turns, but remains visible to the model.
            if iteration == 0 and original_user_message:
                tool_history.insert(0, LLmMessage(role="user", content=original_user_message))
                body.pop("user_message", None)

            # Execute each tool call and collect results
            for tool_call in response.tools:
                result = self._execute_tool_call(tool_call.name, tool_call.parameters, node)
                logger.debug(f"Tool '{tool_call.name}' returned: {result[:120]}")
                accumulated_tool_results.append(result)

                tool_history.append(LLmMessage(
                    role="assistant",
                    content=f"[tool_call] {tool_call.name}({json.dumps(tool_call.parameters)})"
                ))
                tool_history.append(LLmMessage(
                    role="user",
                    content=f"[tool_result] {tool_call.name}: {result}"
                ))

            # tool node (inferred): stop after executing tools if results will be passed downstream
            if (node.mcp_servers or node.tools) and node.message_passing.output:
                response.tool_results = accumulated_tool_results
                return response

        logger.warning(f"Node '{node.id}' hit tool loop limit ({MAX_ITERATIONS} iterations)")
        return response

    def _execute_tool_call(self, name: str, parameters: dict, node: GraphNode) -> str:
        """Route a tool call to either a static executor or an MCP server."""
        # 1. Try MCP first
        mcp_handler = self._mcp_server_for_tool(name, node)
        if mcp_handler:
            return mcp_handler.call_tool(name, parameters)

        # 2. Try static executor
        executor = self.tool_executors.get(name)
        if executor:
            result = executor(**parameters)
            return str(result)

        raise RuntimeError(
            f"Node '{node.id}': no executor registered for tool '{name}'. "
            f"Register it via tool_executors={{'{name}': fn}} in Compiler()"
        )

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

    def _mcp_tools_for_node(self, node: GraphNode) -> list:
        """Return LLMTool list from all MCP servers assigned to this node."""
        if not node.mcp_servers:
            return []
        tools = []
        for server_id in node.mcp_servers:
            handler = self.mcp_handlers.get(server_id)
            if handler:
                tools.extend(handler.list_tools())
            else:
                logger.warning(f"MCP server '{server_id}' not connected — skipping for node '{node.id}'")
        return tools

    def _mcp_server_for_tool(self, tool_name: str, node: GraphNode) -> McpHandler | None:
        """Return the McpHandler that owns the given tool name, for this node."""
        if not node.mcp_servers:
            return None
        for server_id in node.mcp_servers:
            handler = self.mcp_handlers.get(server_id)
            if handler and tool_name in handler.tool_names():
                return handler
        return None

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

        all_tools = []
        if self._tools_check(node):
            all_tools.extend(compose_tools(self.tools, node.tools))
        all_tools.extend(self._mcp_tools_for_node(node))
        if all_tools:
            body["tools_data"] = all_tools

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
            if (node.mcp_servers or node.tools) and response.tool_results:
                self.message_passing.extend(response.tool_results)
            elif response.messages is not None and len(response.messages) > 0:
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
                    md += f"""```json\n {json.dumps([t.model_dump() for t in output.response.tools], indent=4)} \n```\n"""
                if output.response.tool_results is not None:
                    md += f"""```\n{chr(10).join(output.response.tool_results)}\n```\n"""
                md += f"\nToken Input size:  {output.response.input_size} \n "
                md += f" Token Output size:  {output.response.output_size} \n "

        with open(path, "w") as f:
            f.write(md)
