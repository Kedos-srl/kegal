#  Documentation – `Graph` Framework

Below is a detailed description of every Pydantic model that constitutes the `Graph` class hierarchy.  
For each model we list the fields, their types, optionality, and provide concrete YAML and JSON examples that represent a minimal valid instance of the model.

> **Note**: All models are defined in `kegal/graph.py` (or the corresponding `graph.py` file). They are used to serialise, deserialise, and validate graph configurations.

---

## Architecture overview

```mermaid
graph TD
    subgraph Config["Graph YAML / JSON"]
        M["models\n(LLM providers)"]
        P["prompts\n(templates)"]
        N["nodes\n(LLM call units)"]
        E["edges\n(topology)"]
        RCP["react_compact_prompts\n(optional)"]
    end

    M -- index --> N
    P -- index --> N
    N -- declared in --> E

    subgraph Compiler
        DAG["DAG Scheduler\n_build_dag()"]
        EXEC["Executor\ncompile()"]
        REACT["ReAct Loop\n_run_react_loop()"]
    end

    E --> DAG
    DAG --> EXEC
    EXEC -- controller node --> REACT
    RCP -- compaction prompt --> REACT
```

---

## 1. `GraphModel`

| Field             | Type           | Optional | Description |
|------------------|----------------|----------|-------------|
| `llm`            | `str`          | No       | Identifier of the LLM provider (e.g. `"anthropic_aws"`). |
| `model`          | `str`          | No       | Full model name or ARN (e.g. `"arn:aws:bedrock:...:claude-sonnet-4-5-20250929-v1:0"`). |
| `api_key`        | `str` \| `None`| Yes      | API key if required. |
| `host`           | `str` \| `None`| Yes      | Custom host endpoint. |
| `context_window` | `int` \| `None`| Yes      | Token context window of the model (e.g. `32768`). When set, used as the compaction threshold in the ReAct `resume` feature instead of `max_tokens`, and shown as a context-utilization percentage in markdown output. |
| `aws_region_name`| `str` \| `None`| Yes      | AWS region when using Bedrock. |
| `aws_access_key` | `str` \| `None`| Yes      | AWS access key. |
| `aws_secret_key` | `str` \| `None`| Yes      | AWS secret key. |


Provided Models
- anthropic_aws
- anthropic
- bedrock
- ollama
- openai

### YAML Example

```yaml
llm: "ollama"
model: "qwen2.5:7b"
host: "http://localhost:11434"
context_window: 32768   # optional — enables accurate resume threshold and utilization output
```


### JSON Example

```json
{
  "llm": "ollama",
  "model": "qwen2.5:7b",
  "host": "http://localhost:11434",
  "context_window": 32768
}
```


---

## 2. `GraphInputData`

| Field     | Type              | Optional | Description |
|-----------|-------------------|----------|-------------|
| `uri`     | `str` \| `None`   | Yes      | Remote or local path to the file (PDF, image, etc.). |
| `base64`  | `str` \| `None`   | Yes      | Base-64 encoded content. |
| `template`| `dict[str, Any]` \| `None` | Yes | Optional template data for the node that consumes the input. |



*Only one of `uri` or `base64` should be provided for a given instance.*

### YAML Example

```yaml
uri: "https://example.com/documents/report.pdf"
```


### JSON Example

```json
{
  "uri": "https://example.com/documents/report.pdf"
}
```


---

## 3. `NodePrompt`

| Field               | Type                     | Optional | Description |
|---------------------|--------------------------|----------|-------------|
| `template`          | `int`                    | No       | Index of the prompt template in the global `prompts` list. |
| `prompt_placeholders` | `dict[str, Any]` \| `None` | Yes      | Key/value map used to substitute placeholders in the prompt template. |
| `user_message`      | `bool` \| `None`         | Yes      | Whether to include the user’s message. |
| `retrieved_chunks`  | `bool` \| `None`         | Yes      | Whether to include retrieved document chunks. |
| `chat_history`      | `str` \| `None`          | Yes      | Key into the top-level `chat_history` map; injects conversation history into this node’s LLM call. |


### YAML Example

```yaml
template: 1
user_message: true
retrieved_chunks: true
prompt_placeholders:
  analysis_focus: "economic benefits"
```


### JSON Example

```json
{
  "template": 1,
  "user_message": true,
  "retrieved_chunks": true,
  "prompt_placeholders": {
    "analysis_focus": "economic benefits"
  }
}
```


---

## 3.1 Prompt Placeholders

Prompt templates use Python `str.format()` syntax. The following placeholder
names are **reserved** — each is injected automatically when the corresponding
feature is enabled on the node. Using a reserved placeholder without enabling
its feature raises a `KeyError` at `compile()` time (with a descriptive
message). Custom placeholders can be added freely via `prompt_placeholders`.

`Compiler._validate_prompts()` checks all templates at construction time and
emits a `WARNING` for any placeholder that is referenced but not activated.

| Placeholder | Activated by | Content |
|---|---|---|
| `{user_message}` | `prompt.user_message: true` | The string from the top-level `user_message` YAML key or `compiler.user_message`. |
| `{message_passing}` | `message_passing.input: true` | The list of outputs written by upstream nodes with `message_passing.output: true`. |
| `{retrieved_chunks}` | `prompt.retrieved_chunks: true` | The string from the top-level `retrieved_chunks` YAML key or `compiler.retrieved_chunks`. |
| `{blackboard}` | `blackboard.read: true` | The current contents of the shared blackboard buffer at the time the node executes. |
| `{<key>}` | `prompt.prompt_placeholders: {<key>: <value>}` | The literal value from `prompt_placeholders`. Any name that does not clash with the reserved names above is safe to use. |

### Example

```yaml
prompts:
  - template:
      system_template:
        role: |
          You are an analyst specialising in {domain}.   # custom placeholder
      prompt_template:
        context: |
          Previous discussion:
          {blackboard}                                    # reserved — blackboard.read: true required
        user_input: |
          {user_message}                                  # reserved — prompt.user_message: true required

nodes:
  - id: "analyst"
    blackboard:
      read: true
      write: true
    prompt:
      template: 0
      user_message: true
      prompt_placeholders:
        domain: "renewable energy"                        # satisfies {domain}
```

---

## 4. `NodeMessagePassing`

| Field    | Type  | Optional | Description                                        |
|----------|-------|----------|----------------------------------------------------|
| `input`  | `bool`| Yes (default `false`) | Inject the message pipe content into the node’s prompt via `{message_passing}`. |
| `output` | `bool`| Yes (default `false`) | Append this node’s response to the message pipe after execution. |

Both fields default to `false` — the entire `message_passing` block can be omitted from YAML if neither flag is set.

```mermaid
flowchart LR
    A["node_a\noutput: true"] -->|appends to pipe| PIPE[("message\npipe")]
    PIPE -->|"{message_passing}"| B["node_b\ninput: true"]
```

### YAML Example

```yaml
message_passing:
  input: false
  output: true   # this node's response is forwarded downstream
```

### JSON Example

```json
{
  "input": false,
  "output": true
}
```

---

## 5. `NodeBlackboard`

Controls whether a node participates in the shared **blackboard** document —
a persistent markdown buffer written and read across nodes during a single
`compile()` run (implements the [Blackboard architectural pattern](https://en.wikipedia.org/wiki/Blackboard_(design_pattern))).

| Field   | Type   | Optional | Description |
|---------|--------|----------|-------------|
| `read`  | `bool` | No (default `false`) | Inject the current blackboard content into the node's prompt via the `{blackboard}` placeholder. |
| `write` | `bool` | No (default `false`) | Append the node's LLM response to the blackboard after execution. If the blackboard originated from a file it is written back to disk after each write. |

### Node categories

Three behaviour patterns emerge from the `read`/`write` combination:

| Category | `read` | `write` | Role |
|----------|--------|---------|------|
| Cat-1 | `false` | `true`  | **Writer** — seeds the blackboard (e.g. an assistant that drafts the initial content). |
| Cat-2 | `true`  | `true`  | **Enricher** — reads then extends the blackboard (e.g. domain analysts). Multiple Cat-2 nodes run in parallel. |
| Cat-3 | `true`  | `false` | **Reader** — consumes the final blackboard (e.g. a summarizer). |

The compiler infers the correct execution order automatically from these
categories even when the `edges` list is flat (no `children`/`fan_in`
declarations). Cat-1 nodes run first, Cat-2 nodes run in parallel after all
Cat-1 nodes complete, and Cat-3 nodes run after all Cat-2 nodes complete.

### Global `blackboard` key

The top-level `blackboard` key in the graph YAML configures the shared buffer:

```yaml
blackboard: ./path/to/BLACKBOARD.md   # load initial content from a file (writes persist back)
# or
blackboard: "# My Topic\n\n"           # inline markdown seed string
```

If `blackboard` is omitted the buffer starts empty and writes are in-memory
only (no file persistence).

### YAML Example

```yaml
blackboard: ./BLACKBOARD.md

nodes:
  - id: "assistant"
    blackboard:
      read: false
      write: true   # Cat-1: seeds the blackboard
    prompt:
      template: 0
      user_message: true

  - id: "analyst"
    blackboard:
      read: true
      write: true   # Cat-2: enriches the blackboard
    prompt:
      template: 1   # template uses {blackboard}

  - id: "summarizer"
    blackboard:
      read: true
      write: false  # Cat-3: consumes the final blackboard
    prompt:
      template: 2   # template uses {blackboard}
```

The `{blackboard}` placeholder in a prompt template is automatically injected
when `blackboard.read: true` is set on the node. No additional `prompt_placeholders`
entry is needed.

### JSON Example

```json
{
  "read": true,
  "write": false
}
```

---

## 6. `GraphNode`

| Field               | Type                         | Optional | Description |
|---------------------|------------------------------|----------|-------------|
| `id`                | `str`                        | No       | Unique identifier of the node. |
| `model`             | `int`                        | No       | Index of the model in the global `models` list. |
| `temperature`       | `float`                      | No       | Sampling temperature for the LLM. |
| `max_tokens`        | `int`                        | No       | Maximum token length for the LLM response. |
| `show`              | `bool`                       | No       | Whether the node is visible in visualisations. |
| `message_passing`   | `NodeMessagePassing`         | Yes (default `{input: false, output: false}`) | Configuration of input/output passing. |
| `blackboard`        | `NodeBlackboard` \| `None`   | Yes      | Blackboard read/write participation. See §5 `NodeBlackboard`. |
| `prompt`            | `NodePrompt` \| `None`       | Yes      | Prompt configuration. |
| `structured_output` | `dict[str, Any]` \| `None`   | Yes      | JSON schema for the node’s structured output (guard nodes, data extraction). |
| `react_output`      | `dict[str, Any]` \| `None`   | Yes      | JSON schema for the routing output of a ReAct controller. Reserved fields: `next_agent` (str), `done` (bool), `reasoning` (str), `agent_input` (str), `final_answer` (str). |
| `react`             | `NodeReact` \| `None`        | Yes      | ReAct loop config. When set, the node acts as a controller that iteratively dispatches to agents. See §7 `NodeReact`. |
| `images`            | `list[int]` \| `None`        | Yes      | Indices of images to be provided to the node. |
| `documents`         | `list[int]` \| `None`        | Yes      | Indices of documents to be provided to the node. |
| `tools`             | `list[str]` \| `None`        | Yes      | Names of tools (matching the `name` field in the top-level `tools` list) available to this node. |
| `mcp_servers`       | `list[str]` \| `None`        | Yes      | IDs of MCP servers (matching the `id` field in the top-level `mcp_servers` list) available to this node. |

> **Index validation**: `model` and `prompt.template` are validated at `Compiler` construction time. If either index is out of range, a `ValueError` listing all offending nodes is raised before the first `compile()` call.


### YAML Example

```yaml
id: "test_rag_node"
model: 0
temperature: 0.7
max_tokens: 1000
show: true
message_passing:
  input: false
  output: false
prompt:
  template: 1
  user_message: true
  retrieved_chunks: true
  prompt_placeholders:
    analysis_focus: "economic benefits"
structured_output:
  description: "Renewable energy analysis summary"
  parameters:
    validation:
      type: "boolean"
      description: "Whether the message is consistent with the context or not"
    cost_metrics:
      type: "object"
      description: "Cost analysis"
    growth_rate:
      type: "number"
      description: "Annual growth percentage"
    recommendation:
      type: "string"
      description: "Key recommendation"
      enum: ["invest", "wait", "diversify"]
  required:
    - validation
    - cost_metrics
    - growth_rate
    - recommendation
```


### JSON Example

```json
{
  "id": "test_rag_node",
  "model": 0,
  "temperature": 0.7,
  "max_tokens": 1000,
  "show": true,
  "message_passing": {
    "input": false,
    "output": false
  },
  "prompt": {
    "template": 1,
    "user_message": true,
    "retrieved_chunks": true,
    "prompt_placeholders": {
      "analysis_focus": "economic benefits"
    }
  },
  "structured_output": {
    "description": "Renewable energy analysis summary",
    "parameters": {
      "validation": {
        "type": "boolean",
        "description": "Whether the message is consistent with the context or not"
      },
      "cost_metrics": {
        "type": "object",
        "description": "Cost analysis"
      },
      "growth_rate": {
        "type": "number",
        "description": "Annual growth percentage"
      },
      "recommendation": {
        "type": "string",
        "description": "Key recommendation",
        "enum": ["invest", "wait", "diversify"]
      }
    },
    "required": [
      "validation",
      "cost_metrics",
      "growth_rate",
      "recommendation"
    ]
  }
}
```


### Reserved Structured Output Field: `validation`

When a node defines a `structured_output` schema that includes a **`validation`** field of type `boolean`, the compiler treats it as a **gate**. After the node is executed:

- If `validation` is `true` (or the field is absent), compilation continues normally to the next edge or child node.
- If `validation` is `false`, compilation **stops immediately** and no further nodes are executed.

This mechanism is designed for **guard nodes** — nodes whose purpose is to check the user message before the main workflow runs. Typical use cases include:

- **Content moderation**: reject inappropriate or toxic messages.
- **Prompt injection prevention**: detect and block adversarial inputs.
- **Input quality checks**: ensure the user message meets minimum requirements.

#### Example: Guard Node

```yaml
- id: "language_check"
  model: 0
  temperature: 0.3
  max_tokens: 500
  show: true
  message_passing:
    input: false
    output: false
  prompt:
    template: 0
    user_message: true
    retrieved_chunks: false
  structured_output:
    description: "Language appropriateness assessment"
    parameters:
      validation:
        type: "boolean"
        description: "Whether message is appropriate for business use"
      action:
        type: "string"
        description: "Action recommendation"
        enum: ["approve", "reject"]
    required: ["validation", "action"]
```

In this example, if the LLM determines the message is inappropriate, it returns `validation: false` and the graph execution halts before any downstream nodes are reached.

> **Note**: The `validation` field is entirely optional. Nodes without it in their structured output will always allow compilation to proceed.

> **Requirement**: A guard node (one with `validation` in its `structured_output`) **must** have a `prompt` block. Omitting `prompt` on a guard node raises `ValueError` at `compile()` time rather than silently passing the gate.

---

## 7. `NodeReact`

Configuration block for a **ReAct controller** node. Placed inside `GraphNode.react`.

| Field               | Type    | Optional | Default | Description |
|---------------------|---------|----------|---------|-------------|
| `max_iterations`    | `int`   | Yes      | `10`    | Maximum number of agent dispatches before the loop is force-stopped. |
| `resume`            | `bool`  | Yes      | `false` | When `true`, automatically compacts the conversation buffer when it approaches the context limit. |
| `resume_threshold`  | `float` | Yes      | `0.8`   | Fraction of the model's `context_window` (or `max_tokens` if `context_window` is not set) at which compaction is triggered. Only relevant when `resume: true`. |

### ReAct execution loop

```mermaid
flowchart TD
    START([compile]) --> BUILD[Build controller prompt\nfrom node config]
    BUILD --> CALL[Call controller LLM\nwith conversation buffer]
    CALL --> PARSE{Parse routing JSON}
    PARSE -- done=true --> FINAL[Record final answer\nto outputs]
    PARSE -- next_agent=X --> FIND[Find agent edge X\nin react list]
    FIND --> RUN["Run agent subgraph\n(isolated state)"]
    RUN --> OBS[Inject observation\ninto conversation buffer]
    OBS --> RESUME{resume=true and\nthreshold exceeded?}
    RESUME -- yes --> COMPACT[Compact conversation\nwith compact prompt]
    RESUME -- no --> CHECK
    COMPACT --> CHECK{max_iterations\nexceeded?}
    CHECK -- no --> CALL
    CHECK -- yes --> STOP([Stop loop])
    FINAL --> END([End])
    STOP --> END
```

### Agent subgraph isolation

```mermaid
flowchart LR
    subgraph Main["Main Compiler State"]
        MP[message_passing]
        OUT[outputs]
    end
    subgraph Agent["Agent Execution (isolated)"]
        AMP["local message_passing\n(= agent_input)"]
        AN[agent nodes run\nsequentially]
        RES[result extracted]
    end
    MP -->|saved| AMP
    OUT -->|saved| Agent
    AN --> RES
    RES -->|observation| CONV[controller\nconversation buffer]
    AMP -->|restored| MP
    Agent -->|restored| OUT
```

### YAML Example

```yaml
react:
  max_iterations: 8
  resume: true
  resume_threshold: 0.75
```

### Controller vs agent feature support

The controller and agent nodes have different execution paths and therefore support different feature sets.

| Feature | Controller | Agent nodes |
|---|---|---|
| `tools` | ✗ ignored — warning at init | ✓ full tool loop |
| `mcp_servers` | ✗ ignored — warning at init | ✓ full tool loop |
| `blackboard.read` / `.write` | ✗ ignored — warning at init | ✓ writes persist globally across iterations |
| `message_passing.input` | ✓ seeds the initial conversation message | ✓ receives `agent_input` from controller |
| `message_passing.output` | ✓ pushes `final_answer` to the shared buffer | ✓ result observed by controller |
| `images` / `pdfs` | ✓ included in every controller LLM call | ✓ standard behaviour |
| `structured_output` | — overridden by `react_output` | ✓ standard behaviour |
| `chat_history` | ✓ seeds the conversation buffer | ✓ standard behaviour |
| `user_message` | ✓ first user turn in the conversation | ✓ standard behaviour |

**Why tools and MCP are excluded from the controller:** the controller LLM call must return a routing JSON (`react_output`). Mixing a tool loop inside that conversation would create ambiguity — the model cannot simultaneously return routing JSON and invoke tools. If the controller needs to look something up, dispatch a dedicated agent node that has the tool assigned.

---

## 8. `GraphEdge`

| Field      | Type                       | Optional | Description |
|------------|----------------------------|----------|-------------|
| `node`     | `str`                      | No       | Unique identifier of the node this edge entry describes. |
| `children` | `list[GraphEdge]` \| `None`| Yes      | **Fan-out**: nodes to launch in parallel when this node completes. Each entry is itself a `GraphEdge`, allowing recursive sub-structure at any depth. |
| `fan_in`   | `list[GraphEdge]` \| `None`| Yes      | **Aggregation**: nodes this node waits for before starting. This node will not execute until every node listed here has completed. |
| `react`    | `list[GraphEdge]` \| `None`| Yes      | **ReAct agent list**: nodes available to the controller for iterative dispatch. Each entry is a `GraphEdge` (with optional `children`/`fan_in` for multi-step agent subgraphs). Mutually exclusive with `children` and `fan_in`. |

> **Mutual exclusivity**: `react` cannot be combined with `children` or `fan_in` on the same edge entry. `react` + `children` raises a `ValidationError` at parse time; `react` + `fan_in` raises a `ValueError` at `Compiler` construction. Use `message_passing` to order the controller relative to other nodes — the inference stage handles scheduling automatically.

### Dependency semantics

**`edges` describe execution order only** — which node must complete before another can start. Data exchange between nodes is controlled independently by `message_passing` (`input`/`output`) on the nodes themselves.

**Three dependency patterns:**

- `children` (fan-out): node A completes → children B, C, D start in parallel.
- `fan_in` (aggregation): node E starts only when all nodes listed in its `fan_in` have completed.
- `react` (ReAct dispatch): controller C iteratively calls agents from its `react` list until it signals `done: true`.

### Topology diagrams

#### Fan-out

```mermaid
flowchart LR
    A[A] --> B[B]
    A --> C[C]
    A --> D[D]
```

#### Fan-in

```mermaid
flowchart LR
    B[B] --> E[E]
    C[C] --> E
    D[D] --> E
```

#### Fan-out + fan-in

```mermaid
flowchart LR
    A[A] --> B[B]
    A --> C[C]
    A --> D[D]
    B --> E[E]
    C --> E
    D --> E
    E --> F[F]
```

#### ReAct controller

```mermaid
flowchart TD
    CTRL[controller\nReAct loop] -->|iterative dispatch| AGT1[agent_a]
    CTRL -->|iterative dispatch| AGT2[agent_b]
    AGT1 -->|observation| CTRL
    AGT2 -->|observation| CTRL
    CTRL -->|done| OUT([final answer])
```

**Guard nodes** (nodes whose `structured_output` contains a `validation` boolean field) automatically precede all other nodes regardless of edge declarations.

**`message_passing` inference**: if no edges are declared, a node with `output: true` automatically becomes a dependency of any later node with `input: true`, based on their declaration order in the `nodes` list.

### YAML Examples

#### Linear pipeline — no edges required

Two nodes exchanging data via `message_passing` need no edge declarations.
```yaml
nodes:
  - id: "preprocessor"
    message_passing: {input: false, output: true}
    ...
  - id: "analyzer"
    message_passing: {input: true, output: false}
    ...
# edges: omitted — message_passing inference handles ordering
```

#### Fan-out: task decomposition

```yaml
# A completes, then B, C, D run in parallel
edges:
  - node: "A"
    children:
      - node: "B"
      - node: "C"
      - node: "D"
```

#### Fan-in: aggregation

```yaml
# E starts only when B, C, D have all completed
edges:
  - node: "E"
    fan_in:
      - node: "B"
      - node: "C"
      - node: "D"
```

#### Fan-out + fan-in combined

```yaml
# A launches B, C, D in parallel; E waits for all three; E then launches F
edges:
  - node: "A"
    children:
      - node: "B"
      - node: "C"
      - node: "D"
  - node: "E"
    fan_in:
      - node: "B"
      - node: "C"
      - node: "D"
    children:
      - node: "F"
```

> **Note**: B, C, D appear twice — once as `children` of A (who launches them) and once in `fan_in` of E (who waits for them). This is correct and intentional; the two declarations describe different relationships.

#### Nested structure

```yaml
# E waits for B; B itself launches sub-tasks X and Y (fan-out from B)
edges:
  - node: "E"
    fan_in:
      - node: "B"
        children:
          - node: "X"
          - node: "Y"
      - node: "C"
```

> **Note**: `children` always means fan-out (B launches X and Y after B completes). E depends only on B, not on X or Y. If E must also wait for X and Y, declare them explicitly in `fan_in`.

#### ReAct controller with two agents

```yaml
edges:
  - node: "controller"
    react:
      - node: "math_agent"
      - node: "knowledge_agent"
```

The `controller` node runs the ReAct loop; `math_agent` and `knowledge_agent` are **excluded from the main DAG** and only run when the controller dispatches to them.

#### ReAct agent with internal fan-out

```yaml
edges:
  - node: "controller"
    react:
      - node: "research_agent"
        children:
          - node: "web_search"
          - node: "db_lookup"
```

Agent subgraphs can use `children` and `fan_in` internally to structure their own execution.

### JSON Example

```json
{
  "node": "A",
  "children": [
    { "node": "B" },
    { "node": "C" }
  ]
}
```

---

## 9. `Graph`

| Field                   | Type                                   | Optional | Description |
|-------------------------|----------------------------------------|----------|-------------|
| `models`                | `list[GraphModel]`                     | No       | List of LLM configurations. |
| `images`                | `list[GraphInputData]` \| `None`       | Yes      | Image sources used in the graph. |
| `documents`             | `list[GraphInputData]` \| `None`       | Yes      | Document sources used in the graph. |
| `tools`                 | `list[LLMTool]` \| `None`              | Yes      | Tool definitions (from `kegal.llm.llm_model`). Each tool is referenced by its `name` in `GraphNode.tools`. |
| `mcp_servers`           | `list[GraphMcpServer]` \| `None`       | Yes      | MCP server configurations. Each server is referenced by its `id` in `GraphNode.mcp_servers`. |
| `prompts`               | `list[GraphInputData]`                 | No       | Prompt templates (indexed by `NodePrompt.template`). |
| `react_compact_prompts` | `list[GraphInputData]` \| `None`       | Yes      | Compact prompts for ReAct conversation compaction. Accepts `uri` or `template` like regular `prompts`. Index 0 replaces the built-in default compact prompt. |
| `chat_history`          | `dict[str, list[dict[str, str]]]` \| `None` | Yes | Historical messages keyed by scope. |
| `user_message`          | `str` \| `None`                        | Yes      | Current user prompt. |
| `retrieved_chunks`      | `str` \| `None`                        | Yes      | Additional retrieved content (e.g., document snippets). |
| `blackboard`            | `str` \| `None`                        | Yes      | Path to a markdown file or an inline markdown string used as the shared blackboard buffer. See §5 `NodeBlackboard`. |
| `nodes`                 | `list[GraphNode]`                      | No       | All nodes in the graph. |
| `edges`                 | `list[GraphEdge]`                      | No       | Graph topology. |



### DAG execution phases per topological level

```mermaid
flowchart TD
    subgraph Level["Each topological level"]
        P1["Phase 1 — Guard nodes\n(sequential, abort on false)"]
        P2["Phase 2 — Regular nodes\n(parallel if > 1)"]
        P3["Phase 3 — ReAct controllers\n(sequential, after regular nodes)"]
    end
    P1 -->|validation passed| P2
    P2 --> P3
    P1 -->|validation=false| ABORT([Abort graph])
```

### YAML Example (trimmed to essential fields)

```yaml
models:
  - llm: ""
    model: ""
    aws_region_name: ""
    aws_access_key: ""
    aws_secret_key: ""

prompts:
  - template:
      system_template:
        role_and_capabilities: |
          You are a content moderation specialist focused on language appropriateness.
          You evaluate messages for professionalism, toxicity, and business suitability.
        behavioral_guidelines: |
          - Assess language tone and professionalism
          - Detect inappropriate content or toxicity
          - Provide clear approval/rejection decisions
      prompt_template:
        context: |
          Evaluate the user message for appropriateness in business context.
        instruction: |
          Analyze this message: "{user_message}"
          Determine if it's appropriate for business communication.

nodes:
  - id: "language_check"
    model: 0
    temperature: 0.3
    max_tokens: 500
    show: true
    message_passing:
      input: false
      output: false
    prompt:
      template: 0
      user_message: true
      retrieved_chunks: false
    structured_output:
      description: "Language appropriateness assessment"
      parameters:
        validation:
          type: "boolean"
          description: "Whether message is appropriate for business use"
        action:
          type: "string"
          description: "Action recommendation"
          enum: [ "approve",  "reject" ]
      required: [ "validation", "action"]

edges:
  - node: "language_check"
```


### JSON Example (minimal)

```json
{
  "models": [
    {
      "llm": "",
      "model": "",
      "aws_region_name": "",
      "aws_access_key": "",
      "aws_secret_key": ""
    }
  ],
  "prompts": [
    {
      "template": {
        "system_template": {
          "role_and_capabilities": "You are a content moderation specialist focused on language appropriateness.\nYou evaluate messages for professionalism, toxicity, and business suitability.",
          "behavioral_guidelines": "- Assess language tone and professionalism\n- Detect inappropriate content or toxicity\n- Provide clear approval/rejection decisions"
        },
        "prompt_template": {
          "context": "Evaluate the user message for appropriateness in business context.",
          "instruction": "Analyze this message: \"{user_message}\"\nDetermine if it's appropriate for business communication."
        }
      }
    }
  ],
  "nodes": [
    {
      "id": "language_check",
      "model": 0,
      "temperature": 0.3,
      "max_tokens": 500,
      "show": true,
      "message_passing": {
        "input": false,
        "output": false
      },
      "prompt": {
        "template": 0,
        "user_message": true,
        "retrieved_chunks": false
      },
      "structured_output": {
        "description": "Language appropriateness assessment",
        "parameters": {
          "validation": {
            "type": "boolean",
            "description": "Whether message is appropriate for business use"
          },
          "action": {
            "type": "string",
            "description": "Action recommendation",
            "enum": ["approve", "reject"]
          }
        },
        "required": ["validation", "action"]
      }
    }
  ],
  "edges": [
    {
      "node": "language_check"
    }
  ]
}
```


---

## 10. `LLMTool` (from `kegal.llm.llm_model`)

| Field        | Type                                   | Optional | Description |
|--------------|-----------------------------------------|----------|-------------|
| `name`       | `str`                                  | No       | Name of the tool. |
| `description`| `str`                                  | No       | Short description of what the tool does. |
| `parameters` | `dict[str, LLMStructuredSchema]`       | No       | JSON-schema-style parameter definitions. |
| `required`   | `list[str]`                            | No       | List of required parameter names. |


> **Tip**: Use this model when you need to pass structured function‑call capabilities to the LLM.


## 11. `LLMStructuredSchema` (from `kegal.llm.llm_model`)

| Field         | Type                       | Optional | Description |
|---------------|----------------------------|----------|-------------|
| `schema_`     | `str`                      | Yes      | JSON‑schema identifier (`$schema`). |
| `id_`         | `str`                      | Yes      | Unique schema ID (`$id`). |
| `ref`         | `str`                      | Yes      | Reference to another schema (`$ref`). |
| `defs`        | `dict[str, Any]`           | Yes      | Definitions for reusable subschemas (`$defs`). |
| `comment`     | `str`                      | Yes      | Comment for documentation (`$comment`). |
| `type`        | `str` or `list[str]`      | Yes      | JSON‑schema type(s). |
| `enum`        | `list[Any]` or `None`     | Yes      | Allowed literal values. |
| `const`       | `Any`                      | Yes      | Single allowed value. |
| `title`       | `str`                      | Yes      | Short title for the schema. |
| `description` | `str` or `None`           | Yes      | Detailed description. |
| `default`     | `Any`                      | Yes      | Default value if none provided. |
| `examples`    | `list[Any]` or `None`     | Yes      | Example values. |
| `deprecated`  | `bool` or `None`           | Yes      | Flag indicating deprecation. |
| `multipleOf`  | `float` or `int` or `None`| Yes      | For numeric types: multiple constraint. |
| `minimum`     | `float` or `int` or `None`| Yes      | Minimum inclusive value. |
| `maximum`     | `float` or `int` or `None`| Yes      | Maximum inclusive value. |
| `exclusiveMinimum` | `float` or `int` or `None` | Yes | Minimum exclusive value. |
| `exclusiveMaximum` | `float` or `int` or `None` | Yes | Maximum exclusive value. |
| `minLength`   | `int` or `None`           | Yes      | Minimum string length. |
| `maxLength`   | `int` or `None`           | Yes      | Maximum string length. |
| `pattern`     | `str` or `None`           | Yes      | Regex pattern for strings. |
| `format`      | `str` or `None`           | Yes      | String format hint (e.g., `date-time`). |
| `prefixItems` | `list[dict[str, Any]]` or `None` | Yes | Array items schema for each position. |
| `minItems`    | `int` or `None`           | Yes      | Minimum number of array items. |
| `maxItems`    | `int` or `None`           | Yes      | Maximum number of array items. |
| `uniqueItems` | `bool` or `None`          | Yes      | Whether array items must be unique. |
| `contains`    | `dict[str, Any]` or `None` | Yes      | Subschema that array must contain. |
| `items`       | `dict[str, Any]` or `bool` or `None` | Yes | Schema for array elements or boolean for all items. |
| `patternProperties` | `dict[str, Any]` or `None` | Yes | Regex pattern keys for object properties. |
| `additionalProperties` | `dict[str, Any]` or `bool` or `None` | Yes | Schema for unspecified object properties. |
| `minProperties` | `int` or `None`         | Yes      | Minimum number of object properties. |
| `maxProperties` | `int` or `None`         | Yes      | Maximum number of object properties. |
| `dependentRequired` | `dict[str, list[str]]` or `None` | Yes | Required properties depending on other properties. |
| `properties`  | `dict[str, Any]` or `None` | Yes | Nested field schemas for objects. |
| `required`    | `list[str]` or `None`    | Yes      | Required properties for objects. |
| `allOf`       | `list[dict[str, Any]]` or `None` | Yes | List of subschemas all must validate. |
| `anyOf`       | `list[dict[str, Any]]` or `None` | Yes | List of subschemas at least one must validate. |
| `oneOf`       | `list[dict[str, Any]]` or `None` | Yes | List of subschemas exactly one must validate. |
| `not_`        | `dict[str, Any]` or `None` | Yes | Schema that must not validate. |
| `if_`         | `dict[str, Any]` or `None` | Yes | Conditional schema if condition holds. |
| `then`        | `dict[str, Any]` or `None` | Yes | Schema to validate if `if_` holds. |
| `else_`       | `dict[str, Any]` or `None` | Yes | Schema to validate if `if_` does not hold. |
| `dependentSchemas` | `dict[str, dict[str, Any]]` or `None` | Yes | Schema depending on property presence. |
| `model_config` | `dict` or `None`        | Yes      | Pydantic model configuration (e.g., `{"extra": "allow"}`). |

### YAML Example
```yaml
type: "string"
enum:
  - "approve"
  - "reject"
description: "Whether the message is appropriate for business use."
```
### JSON Example
```json
{
  "type": "string",
  "enum": ["approve", "reject"],
  "description": "Whether the message is appropriate for business use."
}
```
### YAML Example (Object)
```yaml
type: "object"
description: "User profile information"
properties:
  name:
    type: "string"
    description: "User's full name"
  age:
    type: "integer"
    description: "User's age in years"
  status:
    type: "string"
    enum: ["active", "inactive", "pending"]
    description: "Account status"
required:
  - "name"
  - "status"
```
### JSON Example (Array)
```json
{
  "type": "array",
  "description": "List of approved categories",
  "items": {
    "type": "string",
    "enum": ["technology", "business", "education"]
  }
}
```
This model is used inside `LLMTool.parameters` and `LLMStructuredOutput.parameters` to describe each field of a structured schema the LLM should adhere to or return.




