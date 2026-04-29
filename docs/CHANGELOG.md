# Changelog

All notable changes to KeGAL are documented here.

---

## [0.1.2.9] - 2026-04-29

### Added

- **`GraphModel.context_window`** (`graph.py`) — optional `int` field declaring the model's token context window. When set, it is used by `_maybe_compact` as the compaction threshold denominator (previously `max_tokens` was used, which is the *output* budget — an incorrect proxy). Also stored on the compiler as `Compiler.context_windows: list[int | None]`, parallel to `clients`.
- **`CompiledNodeOutput.context_window`** — the context window of the model used for the node is now recorded in the output object and included in the JSON export.
- **Context utilization in markdown output** — `save_outputs_as_markdown()` now prints `Context utilization: X/Y (Z%)` beneath each node's token counts when `context_window` is set.
- **Controller → downstream `message_passing`** — a ReAct controller with `message_passing.output: true` now actually writes its `final_answer` to the shared message pipe after the loop completes (previously `_check_message_passing` was never called for controllers). A downstream node with `message_passing.input: true` declared after the controller in the edges list receives the final answer automatically — no `fan_in` required; message-passing inference handles ordering exactly as for any two consecutive nodes.
- **Warning for unused controller output** — `_build_react_controller_map()` emits a `WARNING` at init time when a controller has `message_passing.output: true` but no downstream main-DAG node has `message_passing.input: true`.
- **Validation: `react` and `fan_in` mutually exclusive** — `_validate_indices()` now raises `ValueError` if any edge carries both `react` and `fan_in`. These mechanisms are mutually exclusive; use `message_passing` to order dependencies around a controller.
- **`_collect_ordered_main_ids()`** (`compiler.py`) — new helper that returns main-DAG node IDs in DFS pre-order, the same traversal used by `_build_dag` Stage 2. Used by the controller message-passing check to determine downstream consumers.
- **Tutorial 10 extended** — new sub-section "Piping the controller's result to a downstream node" with a complete YAML + Python example showing controller → formatter via `message_passing`.

### Fixed

- **`compose_node_prompt()`** (`compose.py`) — `message_passing` was serialized as a Python list repr (`"['text']"`) via `str(list)`. Now joined with `"\n\n"` so downstream nodes receive clean text.
- **`save_outputs_as_markdown()` — messages missing in default mode** — plain text node responses (`response.messages`) were never written in the default (non-`only_content`) branch. Only `json_output`, `tools`, and `tool_results` were emitted; for regular text-output nodes the markdown contained only token counts.
- **`save_outputs_as_markdown()` — wrong separator position in `only_content` mode** — the `---` separator was appended *after* the current node's content (for `i > 0`), placing it between the wrong pair of nodes. Now inserted *before* the current node for all nodes after the first.
- **`compile()` does not reset `_react_trace`** — calling `compile()` twice on the same instance returned stale trace data from the first run for controllers that did not execute in the second run. `self._react_trace = {}` is now reset at the start of each `compile()` call alongside `outputs` and `message_passing`.
- **`final_answer` set from `reasoning` on every iteration** — `final_answer = routing.get("final_answer") or reasoning` ran unconditionally each iteration, causing intermediate chain-of-thought reasoning to silently overwrite the actual final answer when `done` was not yet set. The assignment is now guarded by `if done:`.
- **`_check_message_passing()` — redundant double condition** — the second `if node.message_passing.output:` after the early-return guard was always `True` at that point. Removed.
- **`_check_react_edge_mixing()` — unreachable `children` branch** — `GraphEdge._check_mutual_exclusivity` already raises `ValidationError` at parse time when both `react` and `children` are set, making the compiler-level check for `children` unreachable. The dead branch was removed; only the `fan_in` check (not covered by the Pydantic validator) remains.

### Removed

- **`GraphNode.chat_history`** (`graph.py`) — dead field never read anywhere in the compiler. Chat history is configured exclusively via `NodePrompt.chat_history`. Removed to avoid user confusion.

---

## [0.1.2.8] - 2026-04-28

### Added

- **ReAct loop** (`compiler.py`, `graph.py`) — iterative Reason+Act execution pattern for controller nodes:
  - **`NodeReact`** model (`graph.py`): `max_iterations` (default 10), `resume` (bool), `resume_threshold` (float 0.8). Set on `GraphNode.react` to mark a node as a ReAct controller.
  - **`GraphNode.react_output`** — JSON schema for the controller's routing output. Reserved fields: `next_agent` (which agent to call), `done` (stop signal), `reasoning` (internal reasoning), `agent_input` (passed to agent), `final_answer` (result when done).
  - **`GraphEdge.react`** — list of available agent subgraph edges on the controller's edge entry. Mutually exclusive with `children` (validated at parse time by Pydantic `model_validator`).
  - **`Graph.react_compact_prompts`** — optional list of `GraphInputData` (same format as `prompts:`) for custom conversation compaction prompts. Index 0 overrides the built-in default compact prompt.
  - **`Compiler._run_react_loop()`** — ReAct execution loop: calls the controller LLM, parses routing JSON, dispatches to the selected agent subgraph, injects the observation into the growing conversation buffer, and repeats until `done: true` or `max_iterations` is reached.
  - **`Compiler._run_react_agent()`** — isolated agent subgraph execution: swaps out global `message_passing` and `outputs` state, runs the subgraph sequentially (no concurrency inside agents), restores state, and returns the agent's text result.
  - **`Compiler._maybe_compact()`** — triggered when `resume: true` and `last_response.input_size ≥ max_tokens × resume_threshold`; calls the LLM with the compact prompt to replace the conversation buffer with a dense state record.
  - **`Compiler.get_react_trace(controller_id)`** — returns a `ReactTrace` object with per-iteration detail: `agent_name`, `agent_output`, `reasoning`, `agent_input`, token counts.
  - **`ReactTrace`** and **`ReactIteration`** Pydantic models — exported from `kegal`.
  - **`Compiler._build_react_controller_map()`** — builds `{controller_id → edge}` at init time.
  - **`Compiler._collect_react_agent_ids()`**, **`_collect_main_edge_ids()`**, **`_find_react_agent_edge()`** — react topology helpers.
  - **`_build_dag()`** extended: react agent nodes are excluded from the main DAG; cycle detection and `ordered_ids` collection both skip react lists.
  - **`compile()`** extended: Phase 3 runs ReAct controllers sequentially after regular nodes at the same level; concurrent controllers at the same level raise `ValueError`.
  - **`_validate_indices()`** extended: detects double-execution (agent node also in main edges) and undefined agent nodes (react agent not in `nodes:`).
  - **`test/test_react.py`** — 32 tests (27 unit, 5 integration): schema validation, DAG exclusion, validate-indices errors, concurrent-controller detection, `_run_react_agent` isolation, `_run_react_loop` with mocked LLM (done signal, max-iterations, unknown agent, trace content, token totals), integration tests against Ollama.
  - **`test/graphs/react_graph.yml`** — reference YAML: controller dispatches to `math_agent` and `knowledge_agent` for a two-part question.

### Fixed

- **`_check_validation_gate()`** — guarded `"validation" in response.json_output` with `isinstance(response.json_output, dict)` to prevent `TypeError` when an agent LLM returns a non-dict JSON value (e.g. a plain integer).

---

## [0.1.2.7] - 2026-04-27

### Added
- **`Compiler._validate_indices()`** — called at the end of `__init__`; checks that every node's `model` index is within the `models` list and every `node.prompt.template` index is within the `prompts` list. All violations are collected and reported in a single `ValueError` before the first `compile()` call, rather than raising an opaque `IndexError` at runtime.
- **`_check_uri_scheme()`** (`utils.py`) — URI allowlist guard; only `https` scheme is permitted for remote URIs. Calling `load_text_from_source`, `load_images_to_base64`, or `load_pdfs_to_base64` with a `http://`, `file://`, or other non-HTTPS URI now raises `ValueError` immediately, preventing SSRF via graph-level `uri` fields.
- **`McpHandler.call_timeout`** — new constructor parameter (default `60 s`) forwarded to `future.result(timeout=...)` for every tool call. Prevents the calling thread — and therefore `compile()` — from blocking indefinitely when an MCP server stalls mid-call.
- **`test/test_bug_fixes.py`** — 30 unit tests (no LLM required) covering all 9 fixes in this release.

### Changed
- **`compile()`** — resets `self.outputs` and `self.message_passing` at the start of each invocation. Previously, calling `compile()` more than once on the same `Compiler` instance accumulated node outputs and token counts from all runs.
- **`_run_tool_loop()`** — removed the early-exit shortcut that skipped the LLM synthesis step for nodes with `message_passing.output=true`. The loop now always gives the LLM a chance to produce a final answer from tool results before returning, regardless of the node's message-passing configuration.

### Fixed
- **`_check_message_passing()`** (`compiler.py`) — nodes with neither `input` nor `output` set previously called `self.message_passing.clear()`, wiping data written by upstream nodes before downstream consumers could read it. The destructive `clear()` has been removed; only nodes with `output=true` may write to the pipe.
- **`LlmAnthropic._tools_data()`** (`llm_anthropic.py`) — `input_schema` was erroneously set to the entire serialised `LLMTool` dict (including `name`, `description`, `parameters`, `required` as siblings). It now correctly wraps the parameters in a JSON Schema object `{"type": "object", "properties": ..., "required": [...]}`, matching the Anthropic API contract.
- **`_run_node()`** (`compiler.py`) — a guard node (one whose `structured_output` contains a `validation` field) with `prompt=None` previously returned `True` unconditionally, silently bypassing the validation gate. It now raises `ValueError` with a descriptive message; non-guard nodes with no prompt continue to return `True` as before.
- **`compose_node_prompt()`** (`compose.py`) — the `placeholders` argument was mutated in place (keys `user_message`, `message_passing`, `retrieved_chunks` were added directly to the caller's dict). A shallow copy is now taken at the start of the function, so the node's `prompt_placeholders` config is never modified between `compile()` calls.

---

## [0.1.2.6] - 2026-04-22

### Added
- **Blackboard pipeline element** — shared markdown buffer implementing the [Blackboard architectural pattern](https://en.wikipedia.org/wiki/Blackboard_(design_pattern)), written and read across nodes during a `compile()` run.
  - `NodeBlackboard` model (`graph.py`): `read` and `write` boolean flags on `GraphNode.blackboard`.
  - `Graph.blackboard` field: accepts a file path (content loaded at init, written back on each update) or an inline markdown string.
  - `Compiler._load_blackboard()` static method: resolves file vs. plain-string blackboard at construction time.
  - `Compiler._update_blackboard()`: thread-safe append of node response to the shared buffer; writes back to disk when a file path was provided.
  - Stage-4 DAG inference in `_build_dag()`: automatic write→read dependency resolution using a three-category rule (Cat-1 writers / Cat-2 enrichers / Cat-3 readers) so parallel enricher nodes and flat `edges` declarations work correctly without explicit `children`/`fan_in`.
  - `{blackboard}` placeholder injected automatically into node prompts when `blackboard.read: true`.
  - `test/test_blackboard.py` — full test suite: `NodeBlackboard` model, YAML parsing, `_load_blackboard`, DAG stage-4 inference, integration tests loading `blackboard_graph.yml`.
  - `test/graphs/blackboard_graph.yml` — 4-node reference graph (assistant → analyst_a ‖ analyst_b → summarizer).
  - `test/graphs/BLACKBOARD.md` — seed file for integration tests.
- **`Compiler._validate_prompts()`** — called at the end of `__init__`; uses `string.Formatter().parse()` to extract all `{placeholder}` tokens from every node's compiled prompt template and emits a `WARNING` for any placeholder that is referenced but not activated in the node config (via `user_message`, `message_passing`, `retrieved_chunks`, `blackboard.read`, or `prompt_placeholders`). Misconfigurations are caught at construction time rather than at `compile()` runtime.
- **`TestValidatePrompts`** (in `test/test_graphs.py`) — 6 unit tests covering warning/no-warning cases for `_validate_prompts()`.
- **`TestRunParallelFailure`** (in `test/test_graphs.py`) — 3 unit tests verifying `_run_parallel` exception propagation.

### Changed
- **`GraphNode.message_passing`** — now has a default of `NodeMessagePassing()` (`{input: false, output: false}`); the field can be omitted from YAML.
- **`Compiler._run_parallel()`** — exceptions from parallel nodes are now collected and re-raised as a single `RuntimeError` (chained to the first cause) after all futures complete. Previously non-guard failures were silently logged, inconsistent with the `raise` behaviour of sequential node execution. Successful sibling results and blackboard writes are preserved before the error propagates.

### Fixed
- **`compose_node_prompt()`** (`compose.py`) — `str.format()` `KeyError` now raises with a descriptive message listing available placeholders and which feature to enable, rather than a bare `KeyError`.
- **Thread safety** — `_record_output` and `_check_message_passing` are now protected by dedicated locks (`_outputs_lock`, `_message_passing_lock`) preventing data races when parallel nodes write concurrently.
- **Guard node error handling** — an exception inside a guard node now returns `False` (treated as a failed gate, aborting the graph) instead of re-raising; non-guard node exceptions re-raise immediately.

---

## [0.1.2.5] - 2026-04-01

### Added
- **`docs/tutorials.md`** — new tutorials file covering: Python tool executors, MCP servers (stdio + SSE + chaining), fan-out / fan-in edges, guard nodes, message passing, structured output, multi-provider graphs, RAG injection.
- **`docs/`** folder moved from `kegal/docs/` to the repository root for discoverability.
- **`test/graphs/fanout_graph.yml`**, **`fanin_graph.yml`**, **`fanout_fanin_graph.yml`** — isolated YAML fixtures for each edge topology.
- **`TestFanOutGraph`**, **`TestFanInGraph`**, **`TestFanOutFanInGraph`** test classes — structural DAG-level checks and full `test_compile` integration tests for each topology.
- **`TestCompilerClose`** — 6 unit tests for `Compiler.close()` lifecycle (no LLM): no-MCP path, idempotency, `mcp_handlers` cleared after close, `disconnect()` called on each handler, LLM client `close()` dispatched when available, graceful skip when unavailable.
- **`test/test_llm_bedrock_unit.py`** — 7 boto3-mocked unit tests for `LlmBedrock`: `close()` method presence, `complete()` does not close client, multiple calls reuse client, `close()` delegates to boto3, `ValueError` on missing constructor params, response parsing.

### Changed
- **`GraphNode.tools`** — changed from `list[int]` (position indices) to `list[str]` (tool names matching `LLMTool.name`). Breaking change for existing YAML graphs.
- **`GraphNode.mcp_servers`** — changed from `list[int]` (position indices) to `list[str]` (server IDs matching `GraphMcpServer.id`). Breaking change for existing YAML graphs.
- **`compose_tools()`** — updated to filter by tool name instead of list index; also fixed pre-existing bug where `.template` (non-existent attribute) was returned instead of the `LLMTool` objects.
- **`Compiler.disconnect()`** renamed to **`Compiler.close()`** — more accurate name (covers both MCP teardown and HTTP client cleanup). MCP handlers are now cleared (`mcp_handlers.clear()`) after shutdown making `close()` safely idempotent.
- **`McpHandler`** rewritten with a single-task async lifecycle (`_session_lifetime` coroutine) — eliminates the `"Attempted to exit cancel scope in a different task"` anyio warning. The background event loop is now explicitly closed on `disconnect()`, eliminating the secondary `ResourceWarning: unclosed event loop`.
- **`LlmBedrock.close()`** added as a proper resource-release method. The `finally: self.client.close()` block that was incorrectly closing the boto3 client after every API call has been removed.

### Fixed
- `LlmBedrock._get_response()` — `self.client.close()` in the `finally` block closed the boto3 client after every call, making any subsequent `complete()` call fail. Moved to an explicit `close()` method.
- `LlmBedrock.__init__` — error message for missing `aws_region_name` incorrectly said `'region_name'`.
- `test_llm_anthropic.py` — wrong import path `kegal.kegal.llm` (double prefix).
- `test_llm_openai.py` — triple-l typo `LllmOpenai`; wrong module path `tests.llm.test_llm`.
- `test_llm_bedrock.py` — wrong module path `tests.llm.test_llm`.

---

## [0.1.2.4] - 2026-03-31

### Changed
- **`GraphEdge` model** (`graph.py`) — `children` is now `list[GraphEdge]` (recursive) instead of `list[str]`; `fan_in: list[GraphEdge]` added for explicit aggregation; `depends_on` removed (breaking change — migrate to `fan_in`).
- **`_build_dag`** (`compiler.py`) — replaced flat iteration with recursive tree traversal (stage 1); stage 2 (`message_passing` inference) and stage 3 (guard nodes) unchanged. Guard-node scope extended to all nodes in the graph, including pure `message_passing` nodes not listed in any edge.
- **`compile()`** — added warning when two or more nodes at the same topological level both have `message_passing.output=true` (non-deterministic concurrent write to the shared message pipe).
- Test graphs updated to `qwen3-vl:8b`.

### Fixed
- Unknown node referenced in `children` now raises `ValueError` instead of `KeyError`.

### Known limitations
- `detect_cycles` catches cycles within a single recursive edge declaration only. Cross-root cycles are caught downstream by `_topological_levels` with a less specific error message.
- Multiple nodes sharing the same MCP server in a fan-out level are safe but their tool calls are serialized on the server's event loop (lower throughput than the parallel count suggests).

---

## [0.1.2.3] - 2026-03-16

### Added
- **DAG execution engine** — graph nodes are now scheduled via a dependency-aware DAG:
  - Phase 1: guard pass — nodes with `validation` in their structured output run first (sequentially); graph aborts if any returns `validation: false`
  - Phase 2: dependency resolution — `message_passing` flags build a DAG; nodes with unresolved input deps block until their provider completes
  - Phase 3: parallel scheduling — independent nodes (no message_passing deps) run concurrently via `ThreadPoolExecutor`
- `dag_graph.yml` test fixture covering guard, dependency, and parallel execution scenarios
- `kegal/tests/prompts.py` — shared LLM test helpers extracted from individual test files
- `test/assets/test_image.png` — 64×64 gradient PNG for multimodal tests

### Changed
- Ollama test model updated to `qwen3-vl:8b` (supports vision)
- Removed `enum` from structured output schemas in test YAML (Ollama JSON format limitation)
- Dead/commented-out code removed across `compiler.py`, `compose.py`, `graph.py`, and LLM modules
- Minor typo and consistency fixes in LLM handler and model files

### Fixed
- Vision test failure caused by an 8×8 pixel test image too small for `qwen3-vl` runner

---

## [0.1.2.2] - 2025

### Added
- Chat history support (`history` boolean flag on nodes)
- AWS Bedrock provider (`llm_bedrock.py`)
- Structured output validation via `validators.py`
- RAG document injection into node prompts

### Changed
- Compiler refactored to support multi-provider graphs
- Graph schema extended with `tools`, `images`, `documents` per node

---

## [0.1.2.1] - 2025

### Added
- Initial public release
- Graph-based agent framework with YAML/JSON configuration
- Support for Anthropic, OpenAI, and Ollama providers
- Structured JSON output enforcement per node
- Validation gate: nodes with `validation` field abort graph on `false`
- Message passing between nodes
