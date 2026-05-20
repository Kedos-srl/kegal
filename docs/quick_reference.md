# KeGAL Quick Reference — Agent Guide for Graph Construction

This document is the single authoritative reference for building KeGAL graphs.
Read it completely before writing any graph YAML. Every rule here reflects
tested, production-verified behaviour.

---

## 1. Graph File Anatomy

A KeGAL graph is a YAML file with these top-level keys:

```yaml
models:       # required — one or more LLM configurations
verbose:      # optional bool — enable verbose logging
user_message: # optional string — default user prompt
mcp_servers:  # optional — out-of-process tool servers
blackboard:   # optional — named shared markdown buffers
tools:        # optional — in-process Python tool schemas
prompts:      # required — prompt templates (0-indexed list)
nodes:        # required — agent nodes
edges:        # required — execution topology
chat_history: # optional — persistent conversation history
```

---

## 2. Models

```yaml
models:
  - llm: "ollama"           # provider: ollama | anthropic | anthropic_aws | openai | bedrock
    model: "qwen2.5:7b"     # model name or ARN
    host: "http://localhost:11434"  # ollama only
    context_window: 32768   # required when using react resume: true
    api_key: "..."          # anthropic / openai
    # aws_region_name, aws_access_key, aws_secret_key for bedrock / anthropic_aws
```

- The list is **0-indexed**. Nodes reference models by index: `model: 0`.
- Multiple entries allow different nodes to use different models/providers.
- `context_window` is required for accurate ReAct compaction. Without it, `max_tokens` is used as a proxy (much smaller).

---

## 3. Prompts

```yaml
prompts:
  - template:                         # index 0
      system_template:
        role: |
          System instruction text.
        any_key: |
          More system text (multiple keys are concatenated).
      prompt_template:
        label_a: |
          {user_message}              # placeholder
        label_b: |
          {message_passing}           # placeholder
```

- The list is **0-indexed**. Nodes reference prompts by index: `prompt.template: 0`.
- `system_template` keys are concatenated to build the system prompt.
- `prompt_template` keys become the user-turn content.
- Template keys are arbitrary labels — they only affect readability.

### Available Placeholders

| Placeholder | Source | Notes |
|---|---|---|
| `{user_message}` | `compiler.user_message` or YAML `user_message:` | Activate with `prompt.user_message: true` on the node |
| `{message_passing}` | accumulated pipe from upstream nodes | Activate with `message_passing.input: true` on the node |
| `{blackboard}` | named board file content | Activate with `blackboard.read: true` on the node |
| `{retrieved_chunks}` | `compiler.retrieved_chunks` | Activate with `prompt.chunks: true` on the node |

---

## 4. Nodes

Every node entry follows this schema:

```yaml
nodes:
  - id: "node_id"               # required — unique string
    model: 0                    # required — index into models list
    temperature: 0.0            # float 0.0–1.0
    max_tokens: 512             # int — max output tokens
    show: true                  # bool — include in output report
    prompt:
      template: 0               # required — index into prompts list
      user_message: true        # inject {user_message} placeholder
      chunks: false             # inject {retrieved_chunks} placeholder
      chat_history: "session"   # named chat history key

    # Data flow
    message_passing:
      input: true               # receive upstream pipe as {message_passing}
      output: true              # write final LLM text to pipe after execution

    # Tools (choose one or both)
    tools: ["tool_name"]        # in-process Python tools (schema declared top-level)
    mcp_servers:                # out-of-process MCP tools
      - id: "server_id"
        tools: ["tool_a"]       # optional whitelist; omit to expose all server tools

    max_tool_calls: 10          # int — max LLM-call iterations in tool loop (default: 10)

    # Shared state
    blackboard:
      id: "board_id"            # must match a declared board
      read: true                # inject board content as {blackboard}
      write: true               # append LLM response to board after execution

    # ReAct controller (mutually exclusive with tools/mcp_servers/blackboard)
    react:
      max_iterations: 20        # int — hard cap on dispatch loop
      resume: true              # enable automatic conversation compaction
      resume_threshold: 0.8     # compact at this fraction of context_window (default: 0.8)
    react_output:               # JSON schema the controller must return each iteration
      type: object
      properties:
        next_agent:   { type: string }
        agent_input:  { type: string }
        done:         { type: boolean }
        final_answer: { type: string }
        reasoning:    { type: string }
      required: ["done"]

    # Structured output (non-ReAct nodes)
    structured_output:
      description: "optional description"
      parameters:
        field_name: { type: string, description: "..." }
        score:      { type: integer }
        valid:      { type: boolean }
      required: ["field_name"]
```

### ReAct Controller Restrictions

| Feature | Controller | Agent nodes |
|---|---|---|
| `tools` | **Raises `ValueError`** | ✓ |
| `mcp_servers` | **Raises `ValueError`** | ✓ |
| `blackboard.write: true` | **Raises `ValueError`** | ✓ |
| `blackboard.read: true` | **Raises `ValueError`** | ✓ |
| `message_passing.input` | ✓ seeds initial conversation | ✓ |
| `message_passing.output` | ✓ pushes `final_answer` downstream | ✓ |

All four restrictions are hard errors raised at `Compiler()` construction — the graph never starts.

---

## 5. Edges

Edges define the execution topology. Nodes NOT referenced in `edges` are still executed — they run in dependency order inferred from `message_passing` flags.

### 5.1 Sequential (linear chain)

The simplest case — no `edges` or bare `edges` list. The scheduler infers order from `message_passing` flags automatically.

```yaml
edges:
  - node: "node_a"    # optional — for readability only
  - node: "node_b"
```

### 5.2 Fan-out: `children` — parallel branches

```yaml
edges:
  - node: "dispatcher"
    children:
      - node: "agent_a"
      - node: "agent_b"
      - node: "agent_c"
```

**`children` means parallel.** All children start simultaneously after the parent completes.
**Never use `children` for sequential intent** — use message_passing ordering instead.
One child is effectively sequential (nothing to run in parallel with), but multiple children always run concurrently.

Children are recursive:
```yaml
edges:
  - node: "A"
    children:
      - node: "B"
        children:
          - node: "D"
          - node: "E"    # D and E run in parallel after B
      - node: "C"        # C runs in parallel with B
```

### 5.3 Fan-in: `fan_in` — aggregation gate

```yaml
edges:
  - node: "synthesizer"
    fan_in:
      - node: "agent_a"
      - node: "agent_b"
      - node: "agent_c"
```

`synthesizer` waits for all listed predecessors. Combine with `children` for fan-out → fan-in:

```yaml
edges:
  - node: "dispatcher"
    children:
      - node: "agent_a"
      - node: "agent_b"
      - node: "agent_c"
  - node: "synthesizer"
    fan_in:
      - node: "agent_a"
      - node: "agent_b"
      - node: "agent_c"
```

A node appears in `children` (who launches it) AND `fan_in` (who waits for it). This double appearance is correct and intentional.

### 5.4 ReAct edges

```yaml
edges:
  - node: "controller"
    react:
      - node: "agent_a"
      - node: "agent_b"
```

Agent nodes listed under `react:` are **excluded from the main DAG** — they only run when the controller dispatches them.

**`react` and `children`/`fan_in` are mutually exclusive on the same edge entry.**

Each entry in `react:` is itself a full `GraphEdge` and may have its own `children`/`fan_in` to define a sub-DAG that runs when that agent is dispatched:

```yaml
edges:
  - node: "controller"
    react:
      - node: "analyze_agent"
        children:
          - node: "writer_agent"    # runs after analyze_agent in sub-graph
      - node: "report_agent"
```

**Sub-graph ordering rule:** Inside a react sub-graph, sequential ordering requires explicit `children`/`fan_in` declarations. The global `message_passing` flag inference does NOT apply within sub-graphs.

---

## 6. Message Passing — Data Flow

Message passing flows text between nodes through a shared pipe.

### How it works

1. A node with `output: true` appends its **final LLM text** to the pipe after execution.
2. A node with `input: true` receives the accumulated pipe as `{message_passing}` in its prompt.

### Output priority (what gets written to the pipe)

1. `response.messages` — the LLM's final text response (always preferred)
2. `response.tool_results` — raw tool output (fallback when no text was produced)
3. `response.json_output` — structured output (last fallback)

**Important:** Even when a node calls tools, it is the **LLM's final text** that flows downstream — not the raw tool results. Design downstream prompts to receive processed findings, not raw data.

### Sequential inference

The scheduler infers `node_a → node_b` automatically when `node_a` has `output: true` and `node_b` has `input: true`, based on declaration order. No explicit edge entries are needed for a linear chain.

### Isolation in ReAct sub-graphs

When the controller dispatches an agent:
- A fresh local pipe is created: `[agent_input]`
- The agent sub-graph runs in isolation against this local pipe
- After the sub-graph completes, the controller receives as **observation**:
  - The pipe growth (everything added beyond the initial `agent_input`)
  - Falls back to the last sub-graph node's `response.messages` if no growth
- The global pipe is restored unchanged after dispatch

---

## 7. Blackboard

Named markdown buffers persisted to disk during `compile()`.

```yaml
blackboard:
  path: ./blackboards/          # directory for board files (relative to YAML)
  boards:
    - id: "findings"
      file: findings.md
      cleanup: true             # truncate at Compiler init (default: true)
    - id: "report"
      file: report.md
      cleanup: true
      import: ["findings"]      # prepend 'findings' content at read time
```

### Node categories

| Category | `read` | `write` | Role |
|---|---|---|---|
| Cat-1 | false | true | Writer — seeds the board |
| Cat-2 | true | true | Enricher — reads then extends |
| Cat-3 | true | false | Reader — consumes final board |

**Execution order is inferred automatically: Cat-1 → Cat-2 (parallel) → Cat-3.** No explicit `children`/`fan_in` needed for this basic pattern.

### Blackboard write behaviour

`write: true` appends the node's `response.messages` (the LLM's final text) to the board file.
**Only use `write: true` on nodes without tools.** A node that calls tools produces noisy intermediate messages mixed with the final text — the blackboard content will be polluted.

For clean blackboard writes from tool-calling workflows, use a dedicated no-tool writer node that receives the findings via `message_passing` and writes them via an MCP `append_text_file` tool, or use a pure `write: true` node that only outputs text.

---

## 8. MCP Servers

Out-of-process tool servers using the Model Context Protocol.

```yaml
mcp_servers:
  - id: "my_tools"
    transport: "stdio"            # stdio | sse
    command: "/path/to/python"    # stdio only — absolute path recommended
    args: ["./server.py"]         # stdio only
    # url: "http://host:8080/sse" # sse only
```

### Attaching to nodes

```yaml
nodes:
  - id: "tool_node"
    mcp_servers: ["my_tools"]             # string shorthand — all tools exposed

  - id: "scoped_node"
    mcp_servers:
      - id: "my_tools"
        tools: ["read_file", "list_dir"]  # whitelist — model only sees these tools
```

**Filter tools per node.** Local LLMs hallucinate less when exposed only to the tools they need.

**`max_tool_calls`** — default 10 LLM-call iterations. Increase for nodes that must read many files:
```yaml
max_tool_calls: 25
```

**MCP servers must be on agent nodes, never on the ReAct controller.**

---

## 9. Python Tool Executors

In-process tools defined as Python functions, wired at `Compiler` construction.

```yaml
# In the YAML
tools:
  - name: "get_weather"
    description: "Returns the current weather for a given city."
    parameters:
      city: { type: string, description: "The city name." }
    required: ["city"]

nodes:
  - id: "tool_node"
    tools: ["get_weather"]
```

```python
# In Python
def get_weather(city: str) -> str:
    return f"Sunny, 22°C in {city}"

with Compiler(uri="graph.yml", tool_executors={"get_weather": get_weather}) as c:
    c.compile()
```

Tool names in `tool_executors` must exactly match names in the YAML `tools:` list.
A node can have both `tools` and `mcp_servers` simultaneously.

---

## 10. ReAct Loop

### Controller prompt requirements

The controller system prompt must declare:
- The available agents and what each does
- The expected JSON output fields
- The workflow / rules

The controller must return `react_output` JSON on every iteration. Key fields:
- `next_agent` — ID of the agent to dispatch (omit only when `done: true`)
- `agent_input` — instruction string passed to the agent
- `done` — `true` only when the full task is complete
- `reasoning` — current state and rationale (helps compaction)
- `final_answer` / `final_summary` — optional summary when done

### Agent node requirements

Agent nodes must have:
- `message_passing: {input: true}` — to receive `agent_input`
- `message_passing: {output: true}` — if the observation should come from the pipe growth
  (otherwise it falls back to `response.messages` of the last sub-graph node)

### Observation extraction priority (what the controller sees)

1. Pipe growth since dispatch start (if any node in the sub-graph has `output: true`)
2. Last sub-graph node's `response.messages`
3. Last sub-graph node's `response.tool_results[-1]`
4. Last sub-graph node's `response.json_output`
5. Echo of `agent_input` (with warning) if nothing produced

### Conversation compaction (resume)

```yaml
react:
  max_iterations: 30
  resume: true
  resume_threshold: 0.8    # compact when conversation > 80% of context_window (default)

models:
  - llm: "ollama"
    model: "qwen3:30b"
    host: "http://..."
    context_window: 32768  # required for accurate threshold calculation
```

Always set `context_window` on the model when using `resume: true`.

### Piping controller output downstream

A controller with `message_passing.output: true` writes its `final_answer` to the shared pipe after the loop ends. Downstream nodes with `input: true` receive it automatically.

---

## 11. Execution Order — DAG Rules

The compiler builds the DAG in four stages:

1. **Structural**: `children` creates fan-out; `fan_in` creates aggregation.
2. **Message passing**: `output: true` node → all later `input: true` nodes (by declaration order).
3. **Guard barrier**: nodes with `validation` in `structured_output` precede all other nodes.
4. **Blackboard**: Cat-1 → Cat-2 (parallel) → Cat-3 (inferred from `read`/`write` flags).

Nodes in the same topological level run **in parallel** (ThreadPoolExecutor). Guard nodes run first within a level, sequentially. The ReAct controller runs last within its level, after all regular nodes complete.

---

## 12. Guard Nodes

A node whose `structured_output` includes a `validation` boolean field becomes a guard. If `validation: false`, the graph aborts immediately and subsequent nodes never run.

```yaml
nodes:
  - id: "input_guard"
    model: 0
    temperature: 0.0
    max_tokens: 64
    show: false
    structured_output:
      parameters:
        validation: { type: boolean, description: "true if input is valid" }
        reason:     { type: string }
      required: ["validation"]
    prompt: { template: 0, user_message: true }
```

Guard nodes are injected automatically before all non-guard nodes. No explicit edge declarations needed.

---

## 13. Multi-Model Assignment

Assign different models to different nodes to optimise cost and speed:

```yaml
models:
  - llm: "ollama"
    model: "qwen3:30b"       # model 0 — strong, for complex reasoning
    host: "http://..."
    context_window: 32768
  - llm: "ollama"
    model: "qwen2.5:14b"     # model 1 — medium, for structured analysis
    host: "http://..."
    context_window: 32768
  - llm: "ollama"
    model: "llama3.2:latest" # model 2 — small, for trivial tasks
    host: "http://..."
    context_window: 8192

nodes:
  - id: "controller"
    model: 0     # strongest model for orchestration
  - id: "analyst"
    model: 1     # medium model for analysis
  - id: "list_agent"
    model: 2     # smallest model for trivial tool calls
```

---

## 14. Critical Rules and Common Pitfalls

### Rule 1 — `children` is parallel, not sequential
Multiple nodes listed under `children` run concurrently. Never use `children` expecting sequential order across siblings.

```yaml
# WRONG — these run in parallel, not in sequence
children:
  - node: "step_1"
  - node: "step_2"  # does NOT wait for step_1

# CORRECT — step_2 waits for step_1
edges:
  - node: "step_1"
    children:
      - node: "step_2"
# Or rely on message_passing order inference for a linear chain.
```

### Rule 2 — ReAct sub-graphs need explicit ordering
Inside a react sub-graph, `message_passing` order inference does NOT apply. Use `children`/`fan_in` for sequential agent pairs:

```yaml
react:
  - node: "analyze"
    children:
      - node: "write"    # write runs AFTER analyze completes
```

### Rule 3 — Controller never has tools, MCP servers, or blackboard access
Setting `tools`, `mcp_servers`, `blackboard.read`, or `blackboard.write` on a controller raises `ValueError` at `Compiler()` construction. Attach all of these to agent nodes only.

### Rule 4 — Blackboard writes must come from no-tool nodes
`blackboard.write: true` appends `response.messages`. A node that also calls tools will pollute the blackboard with tool-call strings. Use a dedicated text-only node for clean writes.

### Rule 5 — `context_window` is required for resume
Without `context_window` on the model, `resume: true` uses `max_tokens` as the budget — far too small, causing premature compaction.

### Rule 6 — Prompt template indices start at 0
Both `models:` and `prompts:` are 0-indexed lists. Index out of range is caught at `Compiler()` construction, not at `compile()`.

### Rule 7 — MCP paths must be absolute on the target machine
The `command` field is executed on the machine running kegal, not the machine authoring the YAML. Use absolute paths for `command` and ensure `args` paths resolve from the working directory where `kegal run` is executed.

### Rule 8 — One MCP server per node reference
The object form `{id: server_id, tools: [...]}` is the correct way to filter tools per node. The string shorthand `"server_id"` exposes all tools.

---

## 15. Complete Working Example — ReAct with Sub-DAG

A controller dispatching a two-step agent pair (analyze → write) and a report agent:

```yaml
models:
  - llm: "ollama"
    model: "qwen3:30b"
    host: "http://localhost:11434"
    context_window: 32768

mcp_servers:
  - id: "files"
    transport: "stdio"
    command: "/path/to/python"
    args: ["./file_server.py"]

blackboard:
  path: ./blackboards/
  boards:
    - id: findings
      file: findings.md
      cleanup: true

prompts:
  # 0 — controller
  - template:
      system_template:
        role: |
          You are an orchestration controller.
          Available agents:
            analyze_agent  — reads and analyses a document; findings go to blackboard
            report_agent   — generates the final report from the blackboard
          Workflow: dispatch analyze_agent for each document, then dispatch report_agent.
          Return JSON: next_agent, agent_input, done, reasoning.
      prompt_template:
        task: "{user_message}"

  # 1 — analyze_agent (reads docs, outputs findings as final text)
  - template:
      system_template:
        role: |
          Read the document at FILE. Produce ONLY a structured findings block as your final response.
      prompt_template:
        task: "{message_passing}"

  # 2 — writer_agent (receives findings via message_passing, appends to blackboard file)
  - template:
      system_template:
        role: |
          You receive an instruction block followed by a findings block in {message_passing}.
          Call append_text_file(path=./blackboards/findings.md, content=<findings block>).
          Reply with: "Written."
      prompt_template:
        task: "{message_passing}"

  # 3 — report_agent (reads blackboard, writes report)
  - template:
      system_template:
        role: |
          Read {blackboard}. Write a full report using write_text_file.
          Reply with: "Report written."
      prompt_template:
        findings: "{blackboard}"
        task: "{message_passing}"

nodes:
  - id: "controller"
    model: 0
    temperature: 0.0
    max_tokens: 1536
    show: false
    prompt: { template: 0, user_message: true }
    react:
      max_iterations: 30
      resume: true
      resume_threshold: 0.8     # default

    react_output:
      type: object
      properties:
        next_agent:  { type: string }
        agent_input: { type: string }
        done:        { type: boolean }
        reasoning:   { type: string }
      required: ["done", "next_agent", "agent_input", "reasoning"]

  - id: "analyze_agent"
    model: 0
    temperature: 0.0
    max_tokens: 2048
    max_tool_calls: 15
    show: false
    message_passing: { input: true, output: true }
    mcp_servers:
      - id: "files"
        tools: ["read_text_file", "read_pdf_file"]
    prompt: { template: 1 }

  - id: "writer_agent"
    model: 0
    temperature: 0.0
    max_tokens: 64
    max_tool_calls: 2
    show: false
    message_passing: { input: true, output: false }
    mcp_servers:
      - id: "files"
        tools: ["append_text_file"]
    prompt: { template: 2 }

  - id: "report_agent"
    model: 0
    temperature: 0.0
    max_tokens: 4096
    max_tool_calls: 10
    show: true
    message_passing: { input: true, output: false }
    blackboard: { id: findings, read: true }
    mcp_servers:
      - id: "files"
        tools: ["write_text_file", "append_text_file"]
    prompt: { template: 3 }

edges:
  - node: "controller"
    react:
      - node: "analyze_agent"
        children:
          - node: "writer_agent"   # runs after analyze_agent in the sub-graph
      - node: "report_agent"
```

---

## 16. CLI Usage

```bash
# Run once from the project directory (requires kegal.yml)
kegal run

# kegal.yml specifies the graph file and mode
# graph: validation_graph.yml
# mode: once   (default)
# mode: chat   (interactive loop)
```

`kegal.yml` fields:
```yaml
graph: my_graph.yml          # required — path to graph YAML, relative to kegal.yml
mode: once                   # once (default) | chat
tools_module: ./tools.py     # optional — Python file with tool_executors dict
message: true                # chat mode only — prompt for user_message each turn
chunks: false                # chat mode only — prompt for RAG chunks each turn
```

`tools_module` loads Python tool executors at startup via `importlib`. The
file must define a non-empty `tool_executors = {"name": fn}` dict at module
level. Missing file or missing dict → hard error, exit 1.

---

## 17. Providers Quick Reference

| `llm` value | Provider | Required fields |
|---|---|---|
| `ollama` | Local Ollama | `model`, `host` |
| `anthropic` | Anthropic API | `model`, `api_key` |
| `anthropic_aws` | Claude via Bedrock | `model` (ARN), `aws_region_name`, `aws_access_key`, `aws_secret_key` |
| `bedrock` | AWS Bedrock native | `model`, `aws_region_name`, `aws_access_key`, `aws_secret_key` |
| `openai` | OpenAI API | `model`, `api_key` |
