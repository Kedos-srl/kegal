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

## Documentation

You can find the documentation in the [docs/doc.md](docs/doc.md) file.

We wrote also a quick [guide to prompt](docs/guide_to_prompt.md).

You can fine 


## How To

The `kegal.py` module provides utility functions for working with `GraphData` objects,
including loading from and exporting to various formats, updating with user messages and conversation history, and managing citations.

You can find documentation and examples here: [docs/kegal_py.md](docs/doc.md)


## Copyright

Copyright 2025 by [Kedos srl](https://www.kedos-srl.it/).

This software is released under the [MIT](LICENSE) license.


