import json
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel
from .compose import compose_template_prompt, compose_node_prompt, compose_images, compose_documents, compose_tools
from .graph import Graph, GraphEdge, GraphNode, NodeReact
from .mcp_handler import McpHandler
from .utils import load_contents
from .llm.llm_handler import LlmHandler
from .llm.llm_model import LLmResponse, LLMStructuredOutput, LLMStructuredSchema, LLmMessage

import logging

logger = logging.getLogger(__name__)

_DEFAULT_REACT_COMPACT_PROMPT = {
    "system": (
        "You are a conversation compactor. Compress the conversation history into a dense, "
        "structured record that preserves ALL key findings, tool results, and decisions. "
        "Do not drop any factual content — compact it so reasoning can continue from this record."
    ),
    "user": "Compact the above conversation into a dense state record.",
}


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


class ReactIteration(BaseModel):
    iteration: int
    agent_name: str
    agent_output: str
    reasoning: str | None = None
    agent_input: str | None = None
    controller_input_tokens: int = 0
    controller_output_tokens: int = 0

class ReactTrace(BaseModel):
    controller_id: str
    iterations: list[ReactIteration] = []
    total_iterations: int = 0
    done: bool = False
    final_answer: str | None = None
    total_controller_input_tokens: int = 0
    total_controller_output_tokens: int = 0


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
        self.blackboard, self._blackboard_path = self._load_blackboard(graph.blackboard)
        self._blackboard_lock = threading.Lock()
        self._message_passing_lock = threading.Lock()
        self._outputs_lock = threading.Lock()
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

        self.react_compact_prompts: list[dict[str, str]] = (
            self._load_prompt_inputs(graph.react_compact_prompts)
            if graph.react_compact_prompts else []
        )
        self._react_trace: dict[str, ReactTrace] = {}

        self._validate_indices()
        self._validate_prompts()
        self._react_controllers: dict[str, GraphEdge] = self._build_react_controller_map()

    def __enter__(self) -> "Compiler":
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> bool:
        self.close()
        return False

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
        return Compiler._load_prompt_inputs(graph.prompts)

    @staticmethod
    def _load_prompt_inputs(prompt_inputs) -> list[dict[str, str]]:
        prompts_templates: list[dict[str, str]] = []
        for prompt_input in prompt_inputs:
            if prompt_input.template is not None:
                prompts_templates.append(compose_template_prompt(prompt_input.template))
            elif prompt_input.uri is not None:
                prompts_templates.append(
                    compose_template_prompt(load_contents(prompt_input.uri))
                )
            else:
                raise ValueError("Prompt input must have either 'template' or 'uri' defined")
        return prompts_templates

    @staticmethod
    def _load_blackboard(value: str | None) -> tuple[str, Path | None]:
        """Load blackboard content from a file path or a plain markdown string.

        Returns a (content, path) tuple where path is set only when value
        pointed to an existing file (used later to persist writes back).
        """
        if value is None:
            return "", None
        path = Path(value)
        if path.is_file():
            return path.read_text(encoding="utf-8"), path
        return value, None

    # -------------------------------------------------------------------------
    # React topology helpers
    # -------------------------------------------------------------------------

    def _collect_react_agent_ids(self) -> set[str]:
        """Return IDs of all nodes that appear exclusively inside react lists."""
        agent_ids: set[str] = set()

        def scan_edge(edge: GraphEdge) -> None:
            for react_edge in (edge.react or []):
                self._collect_subgraph_ids(react_edge, agent_ids)
            for child in (edge.children or []):
                scan_edge(child)
            for fi in (edge.fan_in or []):
                scan_edge(fi)

        for root_edge in self.edges:
            scan_edge(root_edge)
        return agent_ids

    def _collect_subgraph_ids(self, edge: GraphEdge, result: set[str]) -> None:
        result.add(edge.node)
        for child in (edge.children or []):
            self._collect_subgraph_ids(child, result)
        for fi in (edge.fan_in or []):
            self._collect_subgraph_ids(fi, result)

    def _collect_main_edge_ids(self) -> set[str]:
        """Return IDs of all nodes in the main edge tree (not inside react lists)."""
        main_ids: set[str] = set()

        def scan_edge(edge: GraphEdge) -> None:
            main_ids.add(edge.node)
            for child in (edge.children or []):
                scan_edge(child)
            for fi in (edge.fan_in or []):
                scan_edge(fi)
            # deliberately do NOT recurse into edge.react

        for root_edge in self.edges:
            scan_edge(root_edge)
        return main_ids

    def _build_react_controller_map(self) -> dict[str, GraphEdge]:
        """Return a map of controller node ID → its edge (which carries the react list)."""
        controllers: dict[str, GraphEdge] = {}

        def scan(edge: GraphEdge) -> None:
            if edge.react:
                controllers[edge.node] = edge
            for child in (edge.children or []):
                scan(child)
            for fi in (edge.fan_in or []):
                scan(fi)

        for root_edge in self.edges:
            scan(root_edge)

        for nid in controllers:
            bb = self.nodes[nid].blackboard if nid in self.nodes else None
            if bb is not None and (bb.read or bb.write):
                logger.warning(
                    f"Node '{nid}' is a ReAct controller — blackboard flags "
                    f"(read={bb.read}, write={bb.write}) are ignored for controllers. "
                    f"Use message_passing on agent nodes to share data with the controller."
                )

        return controllers

    @staticmethod
    def _find_react_agent_edge(controller_edge: GraphEdge, agent_name: str) -> GraphEdge | None:
        for react_edge in (controller_edge.react or []):
            if react_edge.node == agent_name:
                return react_edge
        return None

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def _validate_indices(self) -> None:
        """Raise ValueError early if any node references an out-of-range model or template index."""
        errors: list[str] = []
        n_models = len(self.clients)
        n_prompts = len(self.prompts)

        # React agent nodes must not also appear in the main edge tree
        react_agent_ids = self._collect_react_agent_ids()
        main_edge_ids = self._collect_main_edge_ids()
        for nid in react_agent_ids & main_edge_ids:
            errors.append(
                f"Node '{nid}' appears both in a react list and in the main edge tree. "
                f"React agent nodes must not be used as regular DAG nodes."
            )

        # React agent nodes must be defined in nodes:
        for nid in react_agent_ids:
            if nid not in self.nodes:
                errors.append(
                    f"React agent node '{nid}' is not defined in 'nodes:'"
                )

        for node_id, node in self.nodes.items():
            if node.model >= n_models:
                errors.append(
                    f"Node '{node_id}': model index {node.model} is out of range "
                    f"(graph defines {n_models} model(s), valid indices: 0–{n_models - 1})"
                )
            if node.prompt is not None and node.prompt.template >= n_prompts:
                errors.append(
                    f"Node '{node_id}': template index {node.prompt.template} is out of range "
                    f"(graph defines {n_prompts} prompt(s), valid indices: 0–{n_prompts - 1})"
                )
            if node.prompt is None and self._is_guard_node(node):
                errors.append(
                    f"Node '{node_id}' is a guard node (structured output has a 'validation' field) "
                    f"but has no prompt — a guard node must have a prompt to evaluate the gate."
                )
        if errors:
            raise ValueError("Graph configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    def _validate_prompts(self) -> None:
        """Warn about prompt placeholders referenced in a template but not activated
        in the corresponding node config.

        Called at the end of __init__ so misconfigurations surface before the
        first compile() call rather than at runtime.
        """
        formatter = string.Formatter()

        for node_id, node in self.nodes.items():
            if node.prompt is None:
                continue

            template_idx = node.prompt.template
            if template_idx >= len(self.prompts):
                continue

            template = self.prompts[template_idx]   # {"system": "...", "user": "..."}

            # Collect all top-level placeholder names referenced in this template
            referenced: set[str] = set()
            for part in ("system", "user"):
                text = template.get(part, "")
                try:
                    for _, field_name, _, _ in formatter.parse(text):
                        if field_name is not None:
                            # Normalise "foo.bar" or "foo[0]" → "foo"
                            root = field_name.split(".")[0].split("[")[0]
                            if root:
                                referenced.add(root)
                except (ValueError, KeyError):
                    pass  # Malformed template — will raise at runtime anyway

            if not referenced:
                continue

            # Build the set of placeholders that will be injected at runtime
            activated: set[str] = set()
            if node.prompt.prompt_placeholders:
                activated.update(node.prompt.prompt_placeholders.keys())
            if node.prompt.user_message:
                activated.add("user_message")
            if node.message_passing.input:
                activated.add("message_passing")
            if node.prompt.retrieved_chunks:
                activated.add("retrieved_chunks")
            if node.blackboard is not None and node.blackboard.read:
                activated.add("blackboard")

            missing = referenced - activated
            if missing:
                logger.warning(
                    f"Node '{node_id}': prompt template references placeholder(s) "
                    f"{sorted(missing)} that are not activated in the node config. "
                    f"This will raise a KeyError at compile time. "
                    f"Enable the feature (user_message, message_passing, "
                    f"retrieved_chunks, blackboard.read) or add to prompt_placeholders."
                )

    # -------------------------------------------------------------------------
    # DAG building
    # -------------------------------------------------------------------------

    def _build_dag(self) -> dict[str, set[str]]:
        """Return a dependency map: node_id → set of node_ids that must finish first.

        React agent nodes (inside react lists) are excluded from the main DAG.
        They are executed on demand by _run_react_loop.
        """
        react_agent_ids = self._collect_react_agent_ids()
        # Only main-DAG nodes participate in the topology
        deps: dict[str, set[str]] = {
            node_id: set()
            for node_id in self.nodes
            if node_id not in react_agent_ids
        }
        declared_structure: dict[str, GraphEdge] = {}

        # — Cycle detection ————————————————————————————————————————————————
        def detect_cycles(edge: GraphEdge, path: set[str]) -> None:
            if edge.node in react_agent_ids:
                return
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

            # React agent nodes are not part of the main DAG
            if node_id in react_agent_ids:
                return

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
                if fi_edge.node in deps:
                    deps[node_id].add(fi_edge.node)

            # children: every child depends on node_id
            for child_edge in (edge.children or []):
                traverse(child_edge)             # validate before accessing deps
                if child_edge.node in deps:
                    deps[child_edge.node].add(node_id)

            # react list: do NOT traverse — agent nodes run outside the DAG

        # — Stage 1: explicit dependencies from edge tree ——————————————————
        for root_edge in self.edges:
            detect_cycles(root_edge, set())
            traverse(root_edge)

        # — Stage 2: message_passing inference (unchanged) ————————————————
        # Collect node order via DFS pre-order traversal of the edge tree.
        # Nodes not referenced in any edge are appended in declaration order.
        ordered_ids: list[str] = []

        def collect_ids(e: GraphEdge) -> None:
            if e.node in react_agent_ids:
                return
            if e.node not in ordered_ids:
                ordered_ids.append(e.node)
            for child in (e.children or []):
                collect_ids(child)
            for fi in (e.fan_in or []):
                collect_ids(fi)

        for edge in self.edges:
            collect_ids(edge)

        for node_id in self.nodes:
            if node_id not in ordered_ids and node_id not in react_agent_ids:
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
        guard_ids = [nid for nid, n in self.nodes.items() if self._is_guard_node(n) and nid not in react_agent_ids]
        non_guard_ids = [nid for nid in self.nodes if nid not in guard_ids and nid not in react_agent_ids]
        for nid in non_guard_ids:
            for gid in guard_ids:
                deps[nid].add(gid)

        # — Stage 4: blackboard write→read inference ———————————————————————
        # Nodes are classified into three categories by their blackboard flags:
        #   Cat-1  write=T read=F  pure writers  — seed the blackboard
        #   Cat-2  read=T  write=T enrichers     — read then extend, run in parallel
        #   Cat-3  read=T  write=F pure readers  — consume the final blackboard
        #
        # Dependency rules (applied by declaration order):
        #   Cat-2 depends on all prior Cat-1 nodes (not on sibling Cat-2 nodes)
        #   Cat-3 depends on all prior Cat-1 and Cat-2 nodes
        #
        # This lets enrichers (Cat-2) run in parallel after the writer(s) finish,
        # and the final reader(s) wait for all of them — with flat edge declarations.
        def _fp(nid): return self.nodes[nid].blackboard

        cat1 = [n for n in ordered_ids if _fp(n) and _fp(n).write and not _fp(n).read]
        cat2 = [n for n in ordered_ids if _fp(n) and _fp(n).read  and     _fp(n).write]
        cat3 = [n for n in ordered_ids if _fp(n) and _fp(n).read  and not _fp(n).write]

        for r in cat2:
            for w in cat1:
                if ordered_ids.index(w) < ordered_ids.index(r):
                    deps[r].add(w)

        for r in cat3:
            for w in cat1 + cat2:
                if ordered_ids.index(w) < ordered_ids.index(r):
                    deps[r].add(w)

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
        self.outputs = CompiledOutput()
        self.message_passing = []
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
            react_ids   = [nid for nid in level if nid in self._react_controllers and nid not in guard_ids]
            regular_ids = [nid for nid in level if nid not in guard_ids and nid not in react_ids]

            if len(react_ids) > 1:
                raise ValueError(
                    f"Concurrent react controllers are not allowed. "
                    f"Controllers at the same DAG level: {react_ids}. "
                    f"Restructure the graph so each controller is at a unique level."
                )

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

            # Phase 3 — react controller (always sequential, after regular nodes)
            for nid in react_ids:
                self._run_react_loop(self._react_controllers[nid], self.nodes[nid])

        self.outputs.compile_time = time.time() - global_start

    def _run_parallel(self, node_ids: list[str]):
        """Execute independent nodes concurrently using a thread pool.

        All futures are allowed to complete before raising so that partial
        results and blackboard writes from successful siblings are preserved.
        If any node raises, a RuntimeError is raised after the pool drains.
        """
        with ThreadPoolExecutor(max_workers=len(node_ids)) as executor:
            futures = {
                executor.submit(self._run_node, self.nodes[nid]): nid
                for nid in node_ids
            }
            failures: list[tuple[str, Exception]] = []
            for future in as_completed(futures):
                nid = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.exception(f"Node '{nid}' failed during parallel execution: {e}")
                    failures.append((nid, e))

        if failures:
            failed_ids = [nid for nid, _ in failures]
            first_exc = failures[0][1]
            raise RuntimeError(
                f"Parallel execution failed for node(s) {failed_ids}."
            ) from first_exc

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
            self._update_blackboard(node, response)
            self._check_message_passing(response, node)
            return self._check_validation_gate(response)
        except Exception as e:
            logger.exception(f"Failed to execute node '{node.id}': {e}")
            if is_guard:
                # Guard node errors are treated as a failed validation — abort the graph
                return False
            # Non-guard errors re-raise to fail fast and avoid running dependent
            # nodes with potentially inconsistent state
            raise

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

        logger.warning(f"Node '{node.id}' hit tool loop limit ({MAX_ITERATIONS} iterations)")
        return response

    # -------------------------------------------------------------------------
    # ReAct loop
    # -------------------------------------------------------------------------

    def _run_react_loop(self, controller_edge: GraphEdge, node: GraphNode) -> None:
        """Execute the ReAct reasoning loop for a controller node."""
        react_cfg = node.react or NodeReact()
        client = self.clients[node.model]

        # Build base body (system_prompt, images, docs, etc.) then extract
        base_body = self._build_model_body(node)
        # Use react_output as the routing schema (overrides structured_output)
        if node.react_output is not None:
            base_body["structured_output"] = LLMStructuredOutput(
                json_output=LLMStructuredSchema(**node.react_output)
            )

        system_prompt: str | None = base_body.pop("system_prompt", None)
        initial_user_msg: str | None = base_body.pop("user_message", None)

        # Conversation buffer: grows across iterations
        conversation: list[LLmMessage] = list(base_body.pop("chat_history", None) or [])
        if initial_user_msg:
            conversation.append(LLmMessage(role="user", content=initial_user_msg))

        # Carry-over fields for each LLM call
        call_extras: dict[str, Any] = {
            k: base_body[k] for k in ("structured_output", "imgs_b64", "pdfs_b64")
            if k in base_body
        }

        trace_iters: list[ReactIteration] = []
        total_in = 0
        total_out = 0
        done = False
        final_answer: str | None = None
        start = time.time()

        logger.info(
            f"[ReAct] ── controller '{node.id}' starting "
            f"(max_iterations={react_cfg.max_iterations}) ──────────────────────"
        )

        for iteration in range(react_cfg.max_iterations):
            logger.info(f"[ReAct] ┌─ iteration {iteration + 1}/{react_cfg.max_iterations}")

            response = client.complete(
                system_prompt=system_prompt,
                user_message=None,
                chat_history=conversation,
                temperature=node.temperature,
                max_tokens=node.max_tokens,
                **call_extras,
            )

            total_in += response.input_size
            total_out += response.output_size

            routing = response.json_output or {}
            next_agent = routing.get("next_agent")
            done = bool(routing.get("done", False))
            reasoning = routing.get("reasoning")
            agent_input_str = routing.get("agent_input") or reasoning or ""
            final_answer = routing.get("final_answer") or reasoning

            if reasoning:
                logger.info(f"[ReAct] │  reasoning  : {reasoning}")
            logger.info(
                f"[ReAct] │  next_agent : {next_agent or '—'}   done={done}   "
                f"tokens in={response.input_size} out={response.output_size}"
            )

            # Append controller decision to conversation
            conversation.append(LLmMessage(
                role="assistant",
                content=json.dumps(routing, ensure_ascii=False),
            ))

            if done:
                if final_answer:
                    logger.info(f"[ReAct] │  final answer: {final_answer}")
                logger.info(f"[ReAct] └─ done ✓")
                break

            if not next_agent:
                logger.warning(
                    f"[ReAct] └─ no next_agent and done=False — stopping early"
                )
                break

            agent_edge = self._find_react_agent_edge(controller_edge, next_agent)
            if agent_edge is None:
                available = [e.node for e in (controller_edge.react or [])]
                logger.warning(
                    f"[ReAct] └─ next_agent='{next_agent}' not in react list "
                    f"{available} — stopping"
                )
                break

            logger.info(f"[ReAct] │  → dispatching '{next_agent}'")
            logger.info(f"[ReAct] │    input : {agent_input_str[:120]}"
                        + ("…" if len(agent_input_str) > 120 else ""))
            agent_output = self._run_react_agent(agent_edge, agent_input_str)
            logger.info(f"[ReAct] │    output: {agent_output[:120]}"
                        + ("…" if len(agent_output) > 120 else ""))

            trace_iters.append(ReactIteration(
                iteration=iteration,
                agent_name=next_agent,
                agent_output=agent_output,
                reasoning=reasoning,
                agent_input=agent_input_str,
                controller_input_tokens=response.input_size,
                controller_output_tokens=response.output_size,
            ))

            conversation.append(LLmMessage(
                role="user",
                content=f"[observation from {next_agent}]\n{agent_output}",
            ))

            if react_cfg.resume:
                self._maybe_compact(
                    conversation, node, react_cfg.resume_threshold, response
                )
        else:
            logger.warning(
                f"[ReAct] └─ max_iterations={react_cfg.max_iterations} reached — stopping"
            )

        elapsed = time.time() - start
        logger.info(
            f"[ReAct] ── controller '{node.id}' finished — "
            f"iterations={len(trace_iters)}  done={done}  "
            f"total tokens in={total_in} out={total_out}  "
            f"elapsed={elapsed:.1f}s ────────────────────────"
        )

        final_response = LLmResponse(
            messages=[final_answer] if final_answer else None,
            json_output={
                "done": done,
                "iterations": len(trace_iters),
                "final_answer": final_answer,
            },
            input_size=total_in,
            output_size=total_out,
        )

        enable_history = self._chat_history_check(node)
        self._record_output(node, final_response, elapsed, enable_history)

        self._react_trace[node.id] = ReactTrace(
            controller_id=node.id,
            iterations=trace_iters,
            total_iterations=len(trace_iters),
            done=done,
            final_answer=final_answer,
            total_controller_input_tokens=total_in,
            total_controller_output_tokens=total_out,
        )

    def _run_react_agent(self, agent_edge: GraphEdge, agent_input: str) -> str:
        """Run an agent subgraph in isolation and return its text output."""
        # Build local dependency map for this subgraph
        local_deps: dict[str, set[str]] = {}

        def collect(edge: GraphEdge) -> None:
            nid = edge.node
            if nid not in local_deps:
                local_deps[nid] = set()
            for child in (edge.children or []):
                collect(child)
                local_deps[child.node].add(nid)
            for fi in (edge.fan_in or []):
                collect(fi)
                local_deps[nid].add(fi.node)

        collect(agent_edge)
        levels = self._topological_levels(local_deps)

        # Swap global state for isolated execution
        saved_mp = self.message_passing
        saved_out = self.outputs
        self.message_passing = [agent_input] if agent_input else []
        initial_mp_len = len(self.message_passing)
        self.outputs = CompiledOutput()

        try:
            for level in levels:
                for nid in sorted(level):  # sequential — no concurrency in react agents
                    self._run_node(self.nodes[nid])

            # Result priority: new message_passing entries > last node response
            if len(self.message_passing) > initial_mp_len:
                result = "\n\n".join(str(m) for m in self.message_passing[initial_mp_len:])
            elif self.outputs.nodes:
                last = self.outputs.nodes[-1]
                if last.response.messages:
                    result = "\n\n".join(last.response.messages)
                elif last.response.json_output is not None:
                    result = json.dumps(last.response.json_output, ensure_ascii=False)
                else:
                    logger.warning(
                        f"[ReAct] Agent subgraph '{agent_edge.node}' produced no extractable output "
                        f"— echoing agent_input back to the controller."
                    )
                    result = agent_input
            else:
                logger.warning(
                    f"[ReAct] Agent subgraph '{agent_edge.node}' ran no nodes or produced no output "
                    f"— echoing agent_input back to the controller."
                )
                result = agent_input
        finally:
            self.message_passing = saved_mp
            self.outputs = saved_out

        return result

    def _maybe_compact(
        self,
        conversation: list[LLmMessage],
        node: GraphNode,
        threshold: float,
        last_response: LLmResponse,
    ) -> None:
        """Compact the conversation buffer when it approaches the token budget."""
        if last_response.input_size < node.max_tokens * threshold:
            return

        logger.info(
            f"[ReAct] │  compacting conversation "
            f"({last_response.input_size}/{node.max_tokens} tokens, "
            f"threshold={threshold:.0%})"
        )

        compact_prompt = (
            self.react_compact_prompts[0]
            if self.react_compact_prompts
            else _DEFAULT_REACT_COMPACT_PROMPT
        )

        client = self.clients[node.model]
        compact_response = client.complete(
            system_prompt=compact_prompt.get("system"),
            user_message=compact_prompt.get("user"),
            chat_history=conversation,
            temperature=0.1,
            max_tokens=node.max_tokens,
        )

        if compact_response.messages:
            compacted = "\n".join(compact_response.messages)
            conversation.clear()
            conversation.append(
                LLmMessage(role="user", content=f"[compacted state]\n{compacted}")
            )
            logger.info(f"[ReAct] │  conversation compacted")

    # -------------------------------------------------------------------------
    # Output helpers — react trace
    # -------------------------------------------------------------------------

    def get_react_trace(self, controller_id: str) -> ReactTrace | None:
        """Return the ReAct execution trace for a controller node, or None."""
        return self._react_trace.get(controller_id)

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
        key = node.prompt.chat_history
        if key not in self.chat_history:
            logger.warning(
                f"Node '{node.id}': chat_history key '{key}' not found in provided chat_history — "
                f"node will run without conversation history."
            )
            return False
        return True

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

        if node.blackboard is not None and node.blackboard.read:
            prompt_elements["placeholders"]["blackboard"] = self.blackboard

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
        with self._outputs_lock:
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

    def _update_blackboard(self, node: GraphNode, response: LLmResponse) -> None:
        """Append node response to the shared blackboard buffer.

        Thread-safe: multiple parallel nodes may write concurrently.
        If blackboard originated from a file the updated content is written back.
        """
        if node.blackboard is None or not node.blackboard.write:
            return
        if not response.messages:
            return
        new_content = "\n\n".join(response.messages)
        with self._blackboard_lock:
            if self.blackboard:
                self.blackboard = self.blackboard.rstrip() + "\n\n" + new_content
            else:
                self.blackboard = new_content
            if self._blackboard_path is not None:
                self._blackboard_path.write_text(self.blackboard, encoding="utf-8")

    def _check_message_passing(self, response, node):
        with self._message_passing_lock:
            if not node.message_passing.output:
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
        if isinstance(response.json_output, dict) and "validation" in response.json_output:
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
