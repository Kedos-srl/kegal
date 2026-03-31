# Changelog

All notable changes to KeGAL are documented here.

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
