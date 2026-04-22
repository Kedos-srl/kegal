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

with Compiler(
    uri="path/to/your_graph.yml",
    tool_executors={"search_kb": search_kb},
) as compiler:
    compiler.compile()
    outputs = compiler.get_outputs()
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
3. `Compiler.__init__` connects to each server automatically. `close()`
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
    model: "ministral-3:3b"
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

with Compiler(uri="path/to/graph.yml") as compiler:
    compiler.compile()
    for node in compiler.get_outputs().nodes:
        for msg in node.response.messages or []:
            print(f"[{node.node_id}] {msg}")
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
    model: "ministral-3:3b"
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
with Compiler(uri="path/to/graph.yml") as compiler:
    compiler.retrieved_chunks = my_retriever.query(user_question)
    compiler.user_message = user_question
    compiler.compile()
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

---

## 9. Footprint — shared markdown buffer across nodes

The **footprint** is a persistent markdown document that nodes can read from and
write to during a single `compile()` run. It is the idiomatic way to build
multi-agent pipelines where a writer seeds context, enrichers extend it in
parallel, and a final reader summarises the whole thread.

### Node categories

| Category | `read` | `write` | Role |
|----------|--------|---------|------|
| Cat-1 | `false` | `true`  | **Writer** — seeds the footprint. |
| Cat-2 | `true`  | `true`  | **Enricher** — reads then extends; multiple Cat-2 nodes run in parallel. |
| Cat-3 | `true`  | `false` | **Reader** — consumes the final footprint. |

The execution order (Cat-1 → Cat-2 in parallel → Cat-3) is **inferred
automatically** from the flags even when `edges` is a flat list — no
`children`/`fan_in` declarations are needed.

### Step 1 — Configure the global footprint source

Add `footprints` at the top level of the YAML. It accepts either a file path
(content is loaded at init; writes are persisted back after each node) or an
inline markdown string:

```yaml
footprints: ./FOOTPRINT.md    # file — writes persist to disk
# or
footprints: "# Topic\n\n"     # inline seed — in-memory only
```

### Step 2 — Mark nodes with footprint flags

```yaml
nodes:
  - id: "assistant"          # Cat-1: write only
    model: 0
    temperature: 0.3
    max_tokens: 200
    show: false
    footprint:
      read: false
      write: true
    prompt:
      template: 0
      user_message: true

  - id: "analyst_a"          # Cat-2: read + write (parallel with analyst_b)
    model: 0
    temperature: 0.5
    max_tokens: 400
    show: false
    footprint:
      read: true
      write: true
    prompt:
      template: 1             # template uses {footprints}

  - id: "analyst_b"          # Cat-2: read + write (parallel with analyst_a)
    model: 0
    temperature: 0.5
    max_tokens: 400
    show: false
    footprint:
      read: true
      write: true
    prompt:
      template: 2             # template uses {footprints}

  - id: "summarizer"         # Cat-3: read only
    model: 0
    temperature: 0.5
    max_tokens: 800
    show: true
    footprint:
      read: true
      write: false
    prompt:
      template: 3             # template uses {footprints}

edges:
  - node: "assistant"
  - node: "analyst_a"
  - node: "analyst_b"
  - node: "summarizer"
```

### Step 3 — Reference `{footprints}` in prompt templates

Any node with `footprint.read: true` has the current buffer injected as
`{footprints}`. No extra `prompt_placeholders` entry is required:

```yaml
prompts:
  - template:                        # template 1 — analyst_a
      system_template:
        role: |
          You are a business analyst.
      prompt_template:
        context: |
          State of discussion:
          {footprints}
        instruction: |
          Analyze the main economic implications. Max 200 words.
```

### Step 4 — Run

```python
from kegal import Compiler

with Compiler(uri="path/to/graph.yml") as compiler:
    compiler.compile()
    outputs = compiler.get_outputs()
    for node in outputs.nodes:
        if node.show:
            print(f"[{node.node_id}]")
            for msg in node.response.messages or []:
                print(msg)
```

After `compile()` the `FOOTPRINT.md` file on disk will contain the full
accumulated thread: seed from `assistant`, extensions from both analysts,
ready for the summarizer to consume.

### Overriding the footprint at runtime

You can reset or inject content before compiling:

```python
with Compiler(uri="path/to/graph.yml") as compiler:
    compiler.footprints = "# Custom seed\n\nOverride the YAML-loaded content."
    compiler.compile()
```
