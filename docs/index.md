# KeGAL — Kedos Graph Agent for LLM

KeGAL is a graph-based agent framework for LLMs. Define multi-node workflows in YAML or JSON, where each node is an LLM call, and KeGAL handles scheduling, parallel execution, and data flow automatically.

## Installation

```bash
pip install git+https://github.com/kedos-srl/kegal.git
```

Or clone and install in development mode:

```bash
git clone https://github.com/kedos-srl/kegal.git
cd kegal
pip install -r requirements.txt
pip install -e .
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
- **Multi-provider** — mix Anthropic, OpenAI, Ollama, and AWS Bedrock in one graph
- **Chat history** — inline or file-based scopes with optional auto-append
- **RAG support** — inject retrieved chunks into prompts
- **Context window tracking** — accurate compaction thresholds and utilization percentages

## Supported Providers

| Provider | Identifier |
|---|---|
| Anthropic (direct) | `anthropic` |
| Anthropic via AWS Bedrock | `anthropic_aws` |
| OpenAI | `openai` |
| Ollama (local) | `ollama` |
| AWS Bedrock (Nova) | `bedrock` |
