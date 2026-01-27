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

Or clone and install in development mode:

```bash
git clone https://github.com/kedos-srl/kegal.git
cd kegal
pip install -r requirements.txt
pip install -e .
```

## Documentation

- [Graph Framework Documentation](kegal/docs/graph_doc.md) - Detailed guide on graph configuration and models
- [LLM Framework Documentation](kegal/docs/llm_doc.md) - Guide on LLM providers and integration

## Quick Start

```python
from kegal import Compiler

# Load and compile a graph from YAML configuration
compiler = Compiler(uri="path/to/your_graph.yml")
compiler.compile()

# Get the outputs
outputs = compiler.get_outputs()
```

## Features

- **Graph-based workflows** – define multi-node agent pipelines in YAML or JSON
- **Structured output** – enforce JSON schemas on LLM responses
- **Validation gate** – nodes with a `validation` boolean field in their structured output act as guards: when the LLM returns `validation: false`, the graph execution stops immediately, preventing downstream nodes from running. Useful for content moderation and prompt injection prevention.
- **Message passing** – forward node outputs to downstream nodes
- **Multi-provider support** – use different LLMs in the same graph
- **Chat history** – maintain conversational context across nodes
- **RAG support** – inject retrieved document chunks into prompts

## Supported LLM Providers

- **Anthropic** - Direct API and AWS Bedrock
- **OpenAI** - GPT models
- **Ollama** - Local LLM hosting
- **AWS Bedrock** - Amazon Nova and other models


## TO DO
- Add support for gemini
- Add support for MCP (Model Context Protocol) 
  

## Copyright

Copyright 2025 by [Kedos srl](https://www.kedos-srl.it/).

This software is released under the [MIT](LICENSE) license.


