# Changelog

All notable changes to KeGAL are documented here.

## Table of Contents

- [[0.1.2.9] - 2026-05-19](#0129---2026-05-19)
- [[0.1.2.8] - 2026-05-14](#0128---2026-05-14)
- [[0.1.2.7] - 2026-05-13](#0127---2026-05-13)
- [[0.1.2.6] - 2026-05-13](#0126---2026-05-13)
- [[0.1.2.5] - 2026-05-12](#0125---2026-05-12)
- [[0.1.2.4] - 2026-05-01](#0124---2026-05-01)
- [[0.1.2.3] - 2026-03-16](#0123---2026-03-16)
- [[0.1.2.2] - 2025](#0122---2025)
- [[0.1.2.1] - 2025](#0121---2025)

---

## [0.1.2.9] - 2026-05-19

### Fixed

- **`_check_message_passing` wrong priority** (`compiler.py`) — when a node called tools, raw tool results were forwarded downstream via `message_passing` instead of the LLM's final text response. Priority is now: `response.messages` first (LLM final text, always preferred), `response.tool_results` fallback (when no text was produced), `response.json_output` last fallback. This corrects the documented contract: "only the final text response is forwarded" (Tutorial 08 §5).

- **Controller restrictions hardened** (`compiler.py`) — setting `tools`, `mcp_servers`, or `blackboard.read=True` on a ReAct controller previously logged a `logger.warning` and silently ignored the setting, allowing misconfigured graphs to run without error. All three now raise `ValueError` at `Compiler()` construction, consistent with the existing `blackboard.write=True` error. The graph never starts with an invalid controller configuration.

### Tests

- **Three new test cases** (`test/test_react.py`, `TestReactValidateIndices`) — one per new hard error: `test_controller_with_tools_raises`, `test_controller_with_mcp_servers_raises`, `test_controller_with_blackboard_read_raises`.

### Docs

- **`docs/quick_reference.md`** (was `KEGAL_GRAPH.md`) — new single-page agent guide for building KeGAL graphs, moved to `docs/` and renamed. Covers all YAML fields, execution rules, edge topology, and common pitfalls with source-verified accuracy.
- **`docs/tutorials/12_react_loop.md`** — controller feature table updated: `tools`, `mcp_servers`, `blackboard.read`, `blackboard.write` rows changed from "ignored — warning at init" to "raises `ValueError` at init"; `blackboard.read` and `.write` split into separate rows.
- **`docs/graph_doc.md`** — same table corrections; explanatory note updated to cover blackboard access and the `ValueError`.
- **`docs/index.md`** — added Documentation section with links to quick reference, graph reference, CLI, and tutorials.

---

## [0.1.2.8] - 2026-05-14

### Added

- **`LLMTool` top-level export** — `from kegal import LLMTool` now works without going through `kegal.llm.llm_model`.
- **`LLMStructuredSchema` package export** — `from kegal.llm import LLMStructuredSchema` now works without going through `kegal.llm.llm_model`.
- **Verbose output improvements** (`compiler.py`):
  - Compile start/done summary lines: `compile started — N node(s)` and `compile done — N node(s) in=X out=Y tokens Z.Zs`.
  - Per-node completion line now includes token counts: `✓ node_id (1.2s in=312 out=88)`.
  - Tool results shown at INFO level (truncated to 120 chars), replacing the previous DEBUG-only entry.
  - Tool call lines now carry a `[mcp]` or `[py]` tag to distinguish MCP server tools from Python executor tools.
  - **ANSI color** applied to all verbose output on TTY terminals (auto-detected via `sys.stderr.isatty()`); suppressed automatically on pipes, redirects, and CI. Palette: bold for compile lines, bold cyan for node start/done, blue for tool calls and ReAct dispatch, dark gray for secondary lines (results, reasoning, routing), bold orange for ReAct banners and iteration headers, bold cyan for ReAct done/final-answer. All colors chosen for readability on both dark and light terminal backgrounds.

### Fixed

- **MCP connection failure** (`compiler.py`) — `Compiler.__init__` now re-raises after logging instead of silently continuing. A misconfigured or unavailable MCP server is a hard failure at construction time, not a silent degradation.
- **`llm_model.py` root logger** — two `logging.debug()` calls used the root logger directly, bypassing the `kegal.*` logger namespace and `verbose` mode. Replaced with a module-level `logger = logging.getLogger(__name__)`.
- **Contradictory edge structure** (`compiler.py`) — when the same node ID appeared in two edges with different `children`/`fan_in` definitions, a warning was logged and the first declaration used silently. This is a configuration error; it now raises `ValueError`.
- **LLM provider logging** (`llm_anthropic.py`, `llm_ollama.py`, `llm_openai.py`) — all three providers now call `logger.error(...)` before re-raising `RuntimeError` on endpoint failure, making failures visible in verbose mode. `llm_anthropic.py` had no module-level logger; one was added. `llm_openai.py` also gained exception chaining (`from e`) and had the redundant `"ERROR:"` prefix removed from the message.
- **Malformed prompt template** (`compiler.py`) — the silent `except (ValueError, KeyError): pass` in `_validate_prompts` now logs at `logger.debug` so malformed templates are visible in verbose mode.
- **`_mcp_server_for_tool` miss level** (`compiler.py`) — upgraded from `logger.warning` to `logger.error` since reaching that path after a successful init indicates an unexpected state.
- **CLI unhandled exceptions** (`cli.py`) — `ValueError` and `RuntimeError` raised by `Compiler.__init__` or `compile()` were previously shown as raw Python tracebacks. They are now caught and printed as `Error: …` with exit code 1. In chat mode, per-turn compile errors print the message and continue the loop.
- **CLI silent empty output** (`cli.py`) — when no nodes have `show: true`, the CLI now prints `(no output — set show: true on nodes you want to display)` to stderr instead of producing no output at all.
- **CLI node separator** (`cli.py`) — a blank line is now inserted between consecutive visible-node outputs for readability.
- **CLI `message`/`chunks` in once mode** (`cli.py`) — setting either flag with `mode: once` now prints a warning to stderr; the flags are only meaningful in chat mode.
- **CLI unknown `kegal.yml` keys** (`cli.py`) — unknown keys are now reported as a warning to stderr and ignored, catching typos like `moode: chat`.

### Added (CLI)

- **`kegal --version`** — prints the installed version and exits.

### Changed (docs)

- **`docs/graph_doc.md`** — `verbose` field description expanded to cover all output lines, token counts, tool tags, ANSI color scheme, and TTY guard. `LLMTool` and `LLMStructuredSchema` sections updated with new import shortcuts.
- **`docs/cli.md`** — fully updated: `--version`, error handling section, warnings section, `message`/`chunks` chat-only note, no-output hint.
- **`README.md`** — verbose logging feature bullet added; CLI section updated with `--version`, warning behaviors, error handling; new "Defining tools in Python" subsection with import shortcuts.
- **`docs/graph_doc.md` §12** — output methods (`get_outputs`, `get_outputs_json`, `save_outputs_as_json`, `save_outputs_as_markdown`) documented with parameter tables and examples.

---

## [0.1.2.7] - 2026-05-13

### Added

- **`NodeMcpServerRef`** (`graph_node.py`) — new model for referencing an MCP server on a node. Replaces the plain string ID with a structured object that carries an optional `tools` whitelist.
  - `id: str` — MCP server ID (must match a `GraphMcpServer.id` in the top-level `mcp_servers` list).
  - `tools: list[str] | None` — when set, only the listed tool names are exposed to the LLM for this node; all other tools from the server are hidden.
  - **Backward compatible** — `GraphNode.mcp_servers` still accepts plain strings (`[file_tools]`); the field validator normalises them to `NodeMcpServerRef(id="file_tools")` automatically. String and object forms can be mixed in the same list.
  - Exported from `kegal` and `kegal.graph`.

  ```yaml
  # Shorthand (unchanged, still valid)
  mcp_servers: [file_tools]

  # New object form with tool filtering
  mcp_servers:
    - id: file_tools
      tools: [read_text_file, write_text_file]
  ```

- **`GraphNode.max_tool_calls`** (`graph_node.py`) — optional `int` field. Sets the maximum number of tool-call iterations for this node's internal tool loop. When `None` (default), the loop uses the built-in limit of 10. Increase for nodes that must read many files or call many tools in a single execution.

  ```yaml
  - id: analyst
    max_tool_calls: 25
    mcp_servers:
      - id: file_tools
        tools: [read_text_file, write_text_file]
  ```

### Fixed

- **Tool loop synthesis step** (`compiler.py`) — added a final unconditional LLM call after the tool loop completes, so the model always produces a text synthesis from accumulated tool results rather than returning pending tool calls.
- **MCP tool name validation in `_validate_indices()`** — when `NodeMcpServerRef.tools` is set, each listed tool name is now checked against the server's available tools at init time; unknown tool names raise `ValueError`.
- **`docs/graph_doc.md`** — `GraphNode` field table updated: `mcp_servers` type changed to `list[NodeMcpServerRef]`; `max_tool_calls` row added. New §6.1 `NodeMcpServerRef` subsection with field table and YAML examples.

---

## [0.1.2.6] - 2026-05-13

### Added

- **`Graph.verbose`** (`bool`, default `false`) — when set to `true` in the graph YAML/JSON, enables INFO-level progress logging to stderr for the entire compilation run. Output includes node start and completion with elapsed time, each MCP/Python tool call with its key parameters, and the full ReAct loop trace (iteration, agent dispatched, input/output preview, token counts). All other loggers remain at WARNING level; only the `kegal.*` namespace is promoted to INFO. Logging is configured in `Compiler.__init__` as soon as the graph is loaded, so it covers the validation and MCP connection phases as well.

  ```yaml
  verbose: true
  models:
    ...
  ```

### Fixed

- **Multi-board blackboard cleanup on `compile()`** (`compiler.py`) — boards with `cleanup: true` are now truncated at the start of every `compile()` call, not only at `Compiler.__init__`. Previously, running `compile()` more than once on the same instance caused board content from the first run to bleed into the second.
- **`verbose` logging handler** (`compiler.py`) — the `kegal.*` logger now uses a dedicated `StreamHandler` with `propagate = False` instead of calling `logging.basicConfig`. Prevents duplicate log lines when the caller has already configured the root logger.
- **`llm_ollama.py` — resilient token count parsing** — `prompt_eval_count` and `eval_count` are now read with `.get(..., 0)` instead of `[...]`. Ollama omits these fields on KV-cache hits; the previous bracket access raised `KeyError` and crashed the compiler.

### Changed

- **CLI entry point** — `kegal.cli:main` added to `setup.py` `entry_points`; the `kegal` command is now available after installation.
- **`__version__`** (`kegal/__init__.py`) — synced to `0.1.2.6` to match `setup.py`.

---

## [0.1.2.5] - 2026-05-12

### Changed

- **Dependencies** — `mkdocs` and related packages removed from `requirements.txt`; documentation is now built separately and not pulled in as a runtime or dev dependency.

---

## [0.1.2.4] - 2026-05-01

Large release merging the full `dev_0.1.2.4` development branch into `main`. Introduces breaking changes to graph configuration and several new major features. See the **Migration** section below before upgrading.

### Added

#### Graph model

- **`GraphEdge.children`** — type changed from `list[str]` to `list[GraphEdge]` (recursive), enabling arbitrarily nested fan-out trees in a single `edges:` declaration.
- **`GraphEdge.fan_in`** — new `list[GraphEdge]` field for explicit aggregation; replaces the removed `depends_on` field.
- **`Graph._validate_node_ids`** — Pydantic `model_validator` that raises `ValueError` at parse time if any two nodes share the same `id`.
- **`graph.py` modularised** — the monolithic `graph.py` is split into focused sub-modules: `graph_model.py`, `graph_mcp.py`, `graph_react.py`, `graph_edge.py`, `graph_blackboard.py`, `graph_node.py`. `graph.py` is now a thin re-export hub. All public symbols remain importable from `kegal.graph` unchanged.

#### Multi-board blackboard system

New feature — replaces the non-existent predecessor with a structured multi-board configuration.

- **`GraphBlackboard`** model: `path` (directory relative to the YAML file) + `boards` (list of `BlackboardEntry`).
- **`BlackboardEntry`** model: `id`, `file`, `cleanup` (default `true` — truncate at init), `import` (list of board IDs to prepend when this board is read).
- **`NodeBlackboardRef`** model: `id` (required — which board to access), `read`, `write`.
- **`Compiler._init_boards()`** — initialises all boards at construction time.
- **`Compiler._assemble_board(board_id)`** — assembles full read-time content by concatenating imported boards followed by the board's own content.
- **`{blackboard}`** placeholder injected automatically into node prompts when `blackboard.read: true`.

  ```yaml
  blackboard:
    path: ./
    boards:
      - id: main
        file: BLACKBOARD.md
        cleanup: true

  nodes:
    - id: writer
      blackboard:
        id: main
        read: false
        write: true
    - id: reader
      blackboard:
        id: main
        read: true
        write: false
  ```

#### ReAct loop

Iterative Reason+Act execution pattern for controller nodes.

- **`NodeReact`** model (`graph_react.py`): `max_iterations` (default 10), `resume` (bool), `resume_threshold` (float 0.8). Set on `GraphNode.react` to mark a node as a ReAct controller.
- **`GraphNode.react_output`** — JSON schema for the controller's routing output. Reserved fields: `next_agent`, `done`, `reasoning`, `agent_input`, `final_answer`.
- **`GraphEdge.react`** — list of available agent subgraph edges. Mutually exclusive with `children` (validated at parse time by Pydantic `model_validator`).
- **`Graph.react_compact_prompts`** — optional list of `GraphInputData` for custom compaction prompts.
- **`Compiler._run_react_loop()`** — calls the controller LLM, parses routing JSON, dispatches to the selected agent subgraph, injects the observation, and repeats until `done: true` or `max_iterations` is reached.
- **`Compiler._run_react_agent()`** — isolated agent subgraph execution: saves/restores global `message_passing` and `outputs` state, runs the subgraph sequentially, returns the agent's text result.
- **`Compiler._maybe_compact()`** — triggered when `resume: true` and `input_size ≥ max_tokens × resume_threshold`; compacts the conversation buffer via an LLM call.
- **`Compiler.get_react_trace(controller_id)`** — returns a `ReactTrace` with per-iteration detail.
- **`ReactTrace`** and **`ReactIteration`** — Pydantic models exported from `kegal`.
- **DAG changes** — react agent nodes are excluded from the main DAG; `compile()` Phase 3 runs controllers sequentially after regular nodes at the same level; concurrent controllers at the same level raise `ValueError`.
- **Controller → `message_passing`** — a controller with `message_passing.output: true` writes its `final_answer` to the shared pipe after the loop; downstream nodes receive it automatically.
- **`test/test_react.py`** — 32 tests (27 unit, 5 integration).
- **`test/graphs/react_graph.yml`** — reference graph dispatching to `math_agent` and `knowledge_agent`.

#### Context window

- **`GraphModel.context_window`** (`graph_model.py`) — optional `int` field. When set, used by `_maybe_compact` as the compaction threshold denominator and stored on the compiler as `Compiler.context_windows: list[int | None]`.
- **`CompiledNodeOutput.context_window`** — recorded in output object and JSON export.
- **Context utilization in `save_outputs_as_markdown()`** — prints `Context utilization: X/Y (Z%)` when `context_window` is set.

#### File-based chat history

- **`ChatHistoryFile`** model (`graph_history.py`): `path` (JSON file path) + `auto` (bool, default `false`). Exported from `kegal`.
- **`Graph.chat_history`** — field type extended to `dict[str, list[dict[str, str]] | ChatHistoryFile]`.
- **`Compiler._init_history()`** — resolves all scopes at construction time: inline arrays stored as-is, file-based scopes loaded from disk, remote URLs fetched via `load_text_from_source` (HTTPS only).
- **`Compiler._update_auto_history()`** — called at end of `compile()`; for every `auto` scope, appends user and assistant turns and persists to the JSON file.
- **`Compiler._history_auto_paths`** — dict tracking which scopes require automatic persistence.
- **Scope uniqueness validation** in `_validate_indices()` — each `chat_history` scope key may be referenced by at most one node.
- **`test/test_chat_history.py`** — full test suite.

#### Compiler convenience methods

- **`Compiler.add_chat_history(id, *, file, uri, history)`** — sets `compiler.chat_history[id]` from a local file, an HTTPS URL, or an inline list. Exactly one source required.
- **`Compiler.add_retrieved_chunks(*, file, uri, chunks)`** — sets `compiler.retrieved_chunks` from a local file, an HTTPS URL, or a plain string. Exactly one source required.

#### Validation and safety

- **`Compiler._validate_indices()`** — checks model/template indices, `node.tools` names, `node.mcp_servers` IDs, `node.blackboard.id` references, and `react`/`fan_in` mutual exclusivity at init time; all errors collected and reported in a single `ValueError`.
- **`_check_uri_scheme()`** (`utils.py`) — HTTPS-only URI guard; `http://`, `file://`, and other schemes raise `ValueError` immediately.
- **`McpHandler.call_timeout`** — new constructor parameter (default 60 s) forwarded to every tool call; prevents indefinite blocking when an MCP server stalls.
- **`_validate_prompts()`** — emits `WARNING` for any `{placeholder}` referenced in a prompt template that is not activated in the node config.

#### Infrastructure

- **`compile()`** — resets `outputs`, `message_passing`, and `_react_trace` at the start of every invocation.
- **`_run_parallel()`** — exceptions from parallel nodes are now collected and re-raised as a single `RuntimeError` after all futures complete.
- **`Compiler.close()`** — renamed from `disconnect()`; clears `mcp_handlers` after shutdown, making it safely idempotent.
- **McpHandler** rewritten with a single-task async lifecycle — eliminates anyio cancel-scope warnings and `ResourceWarning: unclosed event loop`.
- **`LlmBedrock.close()`** — proper resource-release method; removed the `finally: self.client.close()` that closed boto3 after every call.

#### Documentation

- **`docs/graph_doc.md`** — full field reference for all Pydantic models.
- **`docs/llm_doc.md`** — LLM providers and `kegal.llm` internals.
- **`docs/tutorials/`** — 13 individual tutorial files covering: structured output, message passing, guard nodes, RAG, chat history, multimodal, fan-out/fan-in, Python tool executors, MCP servers, multi-provider graphs, blackboard, ReAct loop, context window and output saving.

### Fixed

- **`_check_message_passing()`** — nodes with `input=false, output=false` no longer call `clear()` on the message pipe, preserving upstream data for downstream consumers.
- **`LlmAnthropic._tools_data()`** — `input_schema` now correctly wraps parameters in a JSON Schema object `{"type": "object", "properties": ..., "required": [...]}`.
- **`_run_node()`** — a guard node with `prompt=None` now raises `ValueError`; previously returned `True` unconditionally.
- **`compose_node_prompt()`** — takes a shallow copy of `placeholders` at the start; no longer mutates the caller's dict between `compile()` calls.
- **`compose_node_prompt()`** — `message_passing` joined with `"\n\n"` instead of `str(list)`.
- **`save_outputs_as_markdown()`** — plain text node responses now included in default mode.
- **`save_outputs_as_markdown()`** — separator position corrected in `only_content` mode.
- **`compile()` does not reset `_react_trace`** — stale trace data from prior runs no longer returned for controllers that did not execute.
- **`final_answer`** — only set when `done: true`; previously intermediate reasoning overwrote the final answer on every iteration.
- **`_check_validation_gate()`** — guarded with `isinstance(response.json_output, dict)` to prevent `TypeError` on non-dict JSON values.
- **`GraphNode.chat_history`** — dead field (never read by the compiler) removed to avoid user confusion.

### Changed (breaking)

- **`GraphEdge.depends_on`** removed — migrate to `fan_in`.
- **`GraphNode.tools`** — changed from `list[int]` (position indices) to `list[str]` (tool names). Update all YAML graphs.
- **`GraphNode.mcp_servers`** — changed from `list[int]` (position indices) to `list[str]` (server IDs). Update all YAML graphs.
- **`compose_tools()`** — updated to filter by tool name instead of index.

### Migration (0.1.2.3 → 0.1.2.4)

**`GraphNode.tools` and `GraphNode.mcp_servers` — index → name:**

```yaml
# Before (0.1.2.3)
tools: [0, 1]
mcp_servers: [0]

# After (0.1.2.4)
tools: [search, calculator]
mcp_servers: [file_tools]
```

**`GraphEdge.depends_on` → `fan_in`:**

```yaml
# Before (0.1.2.3)
- source: A
  target: C
  depends_on: [B]

# After (0.1.2.4)
- source: A
  children:
    - source: B
      target: C
  fan_in:
    - source: B
      target: C
```

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
