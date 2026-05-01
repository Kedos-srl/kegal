# KeGAL - Kedos Graph Agent for LLM

KeGAL is a graph-based agent framework for LLMs. It enables the development
of workflows structured as graphs, where each node represents an agent, 
and input and output messages are formatted as structured JSON files.

An agent can be designed using prompt engineering for specific tasks. 
Additionally, each agent can utilize tools written in Python to connect to
external knowledge sources. Moreover, agents can invoke external services via HTTP,
allowing seamless integration with various systems.

The core concept of KeGAL is to leverage one or more LLMs to manage workflow
execution within the architecture. Agents contain no traditional code; instead,
everything is controlled by the LLM through its tooling capabilities.

## Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/kedos-srl/kegal.git
```

From `requirements.txt`: 
```
kegal @ git+https://github.com/kedos-srl/kegal.git
```

Or clone and install in development mode:

```bash
git clone https://github.com/kedos-srl/kegal.git
cd kegal
pip install -r requirements.txt
pip install -e .
```

## Documentation

- [Graph Framework](docs/graph_doc.md) - Full field reference for the `Graph` model hierarchy
- [LLM Providers](docs/llm_doc.md) - Guide on LLM providers and integration
- [Tutorials](docs/tutorials.md) - 13 topic tutorials from basics to advanced: structured output, RAG, chat history, blackboard, ReAct, and more
- [Changelog](docs/CHANGELOG.md) - Version history and release notes

## Quick Start

### Basic usage

```python
from kegal import Compiler

compiler = Compiler(uri="path/to/your_graph.yml")
compiler.compile()
outputs = compiler.get_outputs()
```

Always release the compiler when you are done. It frees:
- **MCP servers** — stopped and their background threads joined (only if the graph uses MCP)
- **LLM clients** — HTTP connection pools closed (only if the provider exposes `close()`)

Without it, sockets may remain open until the garbage collector finalises the object,
producing `ResourceWarning` noise in tests and connection leaks in long-running services.

The recommended pattern is the `with` statement — `close()` is called automatically
on exit, even if `compile()` raises:

```python
with Compiler(uri="path/to/your_graph.yml") as compiler:
    compiler.compile()
    outputs = compiler.get_outputs()
```

In `unittest`, use `setUp` / `tearDown`:

```python
class TestMyGraph(unittest.TestCase):
    def setUp(self):
        self.compiler = Compiler(uri="path/to/your_graph.yml")

    def tearDown(self):
        self.compiler.close()

    def test_compile(self):
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        ...
```

### Inspecting outputs

`get_outputs()` returns a `CompiledOutput` object:

```python
outputs = compiler.get_outputs()

for node in outputs.nodes:
    print(f"[{node.node_id}]")
    if node.response.messages:
        for msg in node.response.messages:   # LLM text response (list of strings)
            print(msg)
    if node.response.json_output:
        print(node.response.json_output)     # structured JSON output
    print(node.compiled_time)                # seconds this node took
    if node.context_window:                  # context utilization (when context_window is set)
        pct = node.response.input_size / node.context_window * 100
        print(f"context: {node.response.input_size}/{node.context_window} ({pct:.1f}%)")

print(f"total time : {outputs.compile_time:.2f}s")
print(f"input tokens : {outputs.input_size}")
print(f"output tokens: {outputs.output_size}")
```

All executed nodes are included in `outputs.nodes`. The `show` flag on a node
is a display hint used by `save_outputs_as_markdown()`; it does not filter
what is returned by `get_outputs()`.

### Overriding the user message at runtime

The `user_message` defined in the YAML is the default. You can replace it before
calling `compile()` to drive the same graph with different inputs:

```python
with Compiler(uri="path/to/your_graph.yml") as compiler:
    compiler.user_message = "Explain the risks of nuclear energy."
    compiler.compile()
```

### Loading from a dict

If the graph is built programmatically rather than read from a file, pass a
`source` dict instead of a URI:

```python
graph_dict = {
    "models": [{"llm": "ollama", "model": "ministral-3:3b", "host": "http://localhost:11434"}],
    "user_message": "Hello",
    "prompts": [...],
    "nodes": [...],
    "edges": [...],
}
with Compiler(source=graph_dict) as compiler:
    compiler.compile()
```

For more advanced usage — attaching Python tool executors, MCP servers, fan-out/fan-in
pipelines, guard nodes, RAG, and multi-provider graphs — see [docs/tutorials.md](docs/tutorials.md).

## Features

- **Graph-based workflows** – define multi-node agent pipelines in YAML or JSON
- **Fan-out / fan-in edges** – `children` launches parallel sub-tasks; `fan_in` aggregates multiple branches before continuing; both are recursive and composable
- **Multi-board blackboard pipeline** – multiple named shared markdown boards (`GraphBlackboard`) written and read across nodes; Cat-1 writers seed a board, Cat-2 enrichers extend it in parallel, Cat-3 readers consume the final result. Boards support `import` chains (prepend another board's content at read time) and `cleanup` control (truncate at init or preserve existing content). Execution order is inferred automatically from `blackboard.read/write` flags even with flat edge declarations.
- **ReAct loop** – controller node iteratively reasons and dispatches to specialist agent nodes until it signals `done: true`; supports automatic conversation compaction (`resume: true`) for long loops; controller output flows to downstream nodes via `message_passing` like any regular node
- **Structured output** – enforce JSON schemas on LLM responses
- **Validation gate** – nodes with a `validation` boolean field in their structured output act as guards: when the LLM returns `validation: false`, the graph execution stops immediately, preventing downstream nodes from running. Useful for content moderation and prompt injection prevention.
- **Message passing** – forward node outputs to downstream nodes; ordering inferred automatically from flags and declaration order — no explicit edge required for linear pipelines
- **MCP support** – connect nodes to external tool servers via the Model Context Protocol (stdio and SSE transports)
- **Python tool executors** – attach plain Python callables as tools without running a separate process
- **Multi-provider support** – use different LLMs in the same graph
- **Context window tracking** – declare `context_window` on a model to get accurate `resume` compaction thresholds and per-node context-utilization percentages in markdown output
- **Chat history** – maintain conversational context across nodes; scopes can be inline arrays or external JSON files with optional `auto: true` to let KeGAL append user+assistant turns automatically after each `compile()` call
- **RAG support** – inject retrieved document chunks into prompts
- **Prompt validation** – at `Compiler()` construction, placeholder tokens in every prompt template are checked against the node config; misconfigurations are reported as warnings before the first `compile()` call
- **Safe resource cleanup** – `compiler.close()` releases MCP server processes and LLM HTTP connection pools; idempotent and transport-aware

## Supported LLM Providers

- **Anthropic** - Direct API and AWS Bedrock
- **OpenAI** - GPT models
- **Ollama** - Local LLM hosting
- **AWS Bedrock** - Amazon Nova and other models


## TO DO
- Add support for gemini
  

## Copyright

Copyright 2025 by [Kedos srl](https://www.kedos-srl.it/).

This software is released under the [MIT](LICENSE) license.
