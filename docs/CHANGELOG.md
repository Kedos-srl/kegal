# Changelog

All notable changes to KeGAL are documented here.

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
