# KeGAL — Kedos Graph Agent for LLM

KeGAL is a graph-based agent framework for LLMs. Define multi-node workflows in YAML or JSON, where each node is an LLM call, and KeGAL handles scheduling, parallel execution, and data flow automatically.

## Installation

Install with the provider(s) you need:

```bash
pip install "kegal[ollama]"      # Ollama (local)
pip install "kegal[anthropic]"   # Anthropic
pip install "kegal[openai]"      # OpenAI
pip install "kegal[gemini]"      # Google Gemini
pip install "kegal[aws]"         # AWS Bedrock
pip install "kegal[all]"         # all providers
```

Or clone and install in development mode (all providers):

```bash
git clone https://github.com/kedos-srl/kegal.git
cd kegal
pip install -e ".[all]"
```

## Quick Start

```python
from kegal import Compiler

with Compiler(uri="path/to/your_graph.yml") as compiler:
    compiler.compile()
    outputs = compiler.get_outputs()
```

## Features

- **Graph-based workflows** — define multi-node agent pipelines in YAML or JSON
- **Fan-out / fan-in edges** — parallel branches and aggregation, recursive and composable
- **Multi-board blackboard** — shared markdown buffers written and read across nodes
- **ReAct loop** — iterative reason-and-act controllers with automatic conversation compaction
- **Structured output** — enforce JSON schemas on LLM responses
- **Validation gate** — guard nodes abort the graph on `validation: false`
- **Message passing** — forward outputs between nodes; ordering inferred automatically
- **MCP support** — connect to external tool servers via stdio or SSE
- **Python tool executors** — attach plain Python callables as tools
- **Multi-provider** — mix Anthropic, OpenAI, Ollama, AWS Bedrock, and Google Gemini in one graph
- **Chat history** — inline or file-based scopes with optional auto-append
- **RAG support** — inject retrieved chunks into prompts
- **Context window tracking** — accurate compaction thresholds and utilization percentages

## Documentation

- [Quick Reference](quick_reference.md) — single-page agent guide for building graphs; start here when using an AI assistant to generate YAML
- [Graph reference](graph_doc.md) — full field-by-field schema documentation
- [CLI reference](cli.md) — `kegal run`, `kegal.yml`, and command-line options
- [Tutorials](tutorials.md) — step-by-step examples

## Supported Providers

| Provider | Identifier | Install extra |
|---|---|---|
| Anthropic (direct) | `anthropic` | `kegal[anthropic]` |
| Anthropic via AWS Bedrock | `anthropic_aws` | `kegal[aws]` |
| OpenAI | `openai` | `kegal[openai]` |
| Ollama (local) | `ollama` | `kegal[ollama]` |
| AWS Bedrock (Nova) | `bedrock` | `kegal[aws]` |
| Google Gemini | `gemini` | `kegal[gemini]` |
