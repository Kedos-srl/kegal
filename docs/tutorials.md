# KeGAL Tutorials

Worked examples covering the main features of the framework. Each tutorial is
self-contained — you can read them in any order.

---

## 1. Attaching Python tool executors

Nodes can call Python functions as tools without spinning up a separate process.
Pass a `tool_executors` dict mapping tool names to callables when creating the
`Compiler`.

```python
def search_kb(query: str) -> str:
    # Your retrieval logic here
    return "Relevant content for: " + query

from kegal import Compiler

compiler = Compiler(
    uri="path/to/your_graph.yml",
    tool_executors={"search_kb": search_kb},
)
try:
    compiler.compile()
    outputs = compiler.get_outputs()
finally:
    compiler.close()
```

The tool name must match what the LLM receives in its tool list. Declare the
tool in the YAML under the top-level `tools` key and reference it by index on
each node that should have access to it:

```yaml
tools:
  - name: "search_kb"
    description: "Search the knowledge base for relevant content."
    parameters:
      type: object
      properties:
        query:
          type: string
          description: "The search query."
      required: ["query"]

nodes:
  - id: "research_node"
    model: 0
    temperature: 0.2
    max_tokens: 512
    show: true
    message_passing:
      input: false
      output: false
    tools: ["search_kb"]  # name matching LLMTool.name in the top-level tools list
    prompt:
      template: 0
      user_message: true
```

---

## 2. MCP servers

The [Model Context Protocol](https://modelcontextprotocol.io) lets a node call
tools that live in a separate process (or remote service) rather than in-process
Python functions. KeGAL supports both `stdio` (subprocess) and `sse` (HTTP)
transports.

### How it works

1. Declare the server(s) in the top-level `mcp_servers` list.
2. Reference the server by its list index in the `mcp_servers` field of every
   node that should have access to it.
3. `Compiler.__init__` connects to each server automatically. `disconnect()`
   shuts them all down cleanly.

### Step 1 — Write a server

Any MCP-compatible server works. A minimal example using
[`fastmcp`](https://github.com/jlowin/fastmcp):

```python
# my_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    """Return a greeting for the given name."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### Step 2 — Configure the graph (YAML)

```yaml
models:
  - llm: "ollama"
    model: "ministral-3:8b"
    host: "http://localhost:11434"

mcp_servers:
  - id: "greeter"          # arbitrary identifier
    transport: "stdio"
    command: "python"
    args: ["my_server.py"]

user_message: "What is the greeting for Alice?"

prompts:
  - template:
      system_template:
        role: |
          You are a helpful assistant. Use the greet tool to answer.
      prompt_template:
        instruction: |
          {user_message}

nodes:
  - id: "greeter_node"
    model: 0
    temperature: 0.0
    max_tokens: 128
    show: true
    message_passing:
      input: false
      output: false
    mcp_servers: ["greeter"]   # id matching GraphMcpServer.id in the top-level mcp_servers list
    prompt:
      template: 0
      user_message: true

edges:
  - node: "greeter_node"
```

### Step 3 — Run

```python
from kegal import Compiler

compiler = Compiler(uri="path/to/graph.yml")
try:
    compiler.compile()
    for node in compiler.get_outputs().nodes:
        print(f"[{node.node_id}] {node.response.content}")
finally:
    compiler.close()   # stops the subprocess and closes the socket
```

### SSE transport

For a remote server (e.g. a running HTTP service), use `sse` transport and
provide a `url` instead of `command`/`args`:

```yaml
mcp_servers:
  - id: "remote_tools"
    transport: "sse"
    url: "http://my-tools-service:8080/sse"
```

### Chaining MCP output into the next node

A common pattern is to have one node query a tool and pass its raw output to a
second node for analysis. Set `message_passing.output: true` on the first node
and `message_passing.input: true` on the second; the message-passing inference
stage will schedule them in order automatically:

```yaml
nodes:
  - id: "query_node"
    ...
    message_passing:
      input: false
      output: true          # result is forwarded downstream
    mcp_servers: ["greeter"]

  - id: "analyst_node"
    ...
    message_passing:
      input: true           # receives query_node output as {message_passing}
      output: false
    prompt:
      template: 1           # template uses the {message_passing} placeholder
```

See [graph_doc.md](graph_doc.md) for the full `GraphMcpServer` field reference.

---

## 3. Fan-out and fan-in edges

`children` (fan-out) and `fan_in` are the two edge primitives for parallel
execution. They are recursive and composable.

### Fan-out: dispatch work in parallel

When a node has `children`, those children start simultaneously as soon as the
parent completes:

```yaml
edges:
  - node: "dispatcher"
    children:
      - node: "economic_analyst"
      - node: "environmental_analyst"
```

Execution order: `dispatcher` → `economic_analyst` ‖ `environmental_analyst`

### Fan-in: wait for multiple branches

`fan_in` makes a node wait for every listed node before it starts:

```yaml
edges:
  - node: "synthesizer"
    fan_in:
      - node: "economic_analyst"
      - node: "environmental_analyst"
```

Execution order: `economic_analyst` ‖ `environmental_analyst` → `synthesizer`

### Combined pipeline

```yaml
edges:
  - node: "dispatcher"
    children:
      - node: "economic_analyst"
      - node: "environmental_analyst"
  - node: "synthesizer"
    fan_in:
      - node: "economic_analyst"
      - node: "environmental_analyst"
```

Execution order: `dispatcher` → `economic_analyst` ‖ `environmental_analyst` → `synthesizer`

Both primitives are recursive — a child can itself have `children` or `fan_in`,
enabling arbitrarily deep task trees.

---

## 4. Guard nodes (validation gate)

A guard node is a node whose `structured_output` schema contains a boolean field
named `validation`. When the LLM returns `validation: false`, the compiler
aborts execution and no downstream nodes run. This is the standard pattern for
content moderation and prompt injection prevention.

```yaml
nodes:
  - id: "guard_node"
    model: 0
    temperature: 0.0
    max_tokens: 64
    show: false
    message_passing:
      input: false
      output: false
    structured_output:
      type: object
      properties:
        validation:
          type: boolean
          description: "true if the input is safe to process, false otherwise."
      required: ["validation"]
    prompt:
      template: 0
      user_message: true
```

The guard node does not need to appear in `edges`. KeGAL automatically inserts it
as a barrier: every other node depends on it, so it always runs first.

```python
compiler = Compiler(uri="path/to/graph.yml")
compiler.user_message = "DROP TABLE users;"   # adversarial input
compiler.compile()

outputs = compiler.get_outputs()
executed = {n.node_id for n in outputs.nodes}
# only "guard_node" is in executed — downstream nodes never ran
```

---

## 5. Message passing

Message passing allows one node's response to flow into the next node's prompt as
the `{message_passing}` placeholder.

```yaml
nodes:
  - id: "summarizer"
    ...
    message_passing:
      input: false
      output: true    # this node's response is forwarded

  - id: "analyst"
    ...
    message_passing:
      input: true     # receives the summarizer's response
      output: false
    prompt:
      template: 1     # template must contain {message_passing}
```

```yaml
# template for analyst
prompts:
  - template:
      system_template:
        role: |
          You are an analyst.
      prompt_template:
        context: |
          {message_passing}
        instruction: |
          Based on the above summary, identify the three key risks.
```

The scheduler infers the dependency automatically: `summarizer` is placed at an
earlier topological level than `analyst` without any explicit edge entry.

---

## 6. Structured output

Use `structured_output` on a node to constrain the LLM response to a specific
JSON schema. The compiler parses the response and makes the structured fields
available for downstream use (e.g. guard logic, conditional branching).

```yaml
nodes:
  - id: "classifier"
    model: 0
    temperature: 0.0
    max_tokens: 128
    show: true
    message_passing:
      input: false
      output: false
    structured_output:
      type: object
      properties:
        category:
          type: string
          enum: ["technical", "billing", "general"]
        confidence:
          type: number
      required: ["category", "confidence"]
    prompt:
      template: 0
      user_message: true
```

---

## 7. Multi-provider graphs

Different nodes in the same graph can use different LLM providers. Declare each
model in the top-level `models` list and reference them by index on each node:

```yaml
models:
  - llm: "ollama"
    model: "ministral-3:8b"
    host: "http://localhost:11434"
  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."

nodes:
  - id: "fast_classifier"
    model: 0             # uses Ollama (cheap, fast)
    ...

  - id: "deep_analyst"
    model: 1             # uses Anthropic (more capable)
    ...
```

---

## 8. RAG — injecting retrieved chunks

Pass retrieved document chunks into a node's prompt via the `retrieved_chunks`
field on the compiler (or in the YAML) and reference them with
`{retrieved_chunks}` in a prompt template:

```python
compiler = Compiler(uri="path/to/graph.yml")
compiler.retrieved_chunks = my_retriever.query(user_question)
compiler.user_message = user_question
compiler.compile()
compiler.close()
```

```yaml
prompts:
  - template:
      system_template:
        role: |
          You are a helpful assistant. Answer only from the provided context.
      prompt_template:
        context: |
          {retrieved_chunks}
        question: |
          {user_message}
```

Set `retrieved_chunks: true` on the node's `prompt` block to enable injection:

```yaml
nodes:
  - id: "rag_node"
    ...
    prompt:
      template: 0
      user_message: true
      retrieved_chunks: true
```
