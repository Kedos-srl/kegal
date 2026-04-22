#  Documentation – `Graph` Framework

Below is a detailed description of every Pydantic model that constitutes the `Graph` class hierarchy.  
For each model we list the fields, their types, optionality, and provide concrete YAML and JSON examples that represent a minimal valid instance of the model.

> **Note**: All models are defined in `kegal/graph.py` (or the corresponding `graph.py` file). They are used to serialise, deserialise, and validate graph configurations.

---

## 1. `GraphModel`

| Field             | Type           | Optional | Description |
|------------------|----------------|----------|-------------|
| `llm`            | `str`          | No       | Identifier of the LLM provider (e.g. `"anthropic_aws"`). |
| `model`          | `str`          | No       | Full model name or ARN (e.g. `"arn:aws:bedrock:...:claude-sonnet-4-5-20250929-v1:0"`). |
| `api_key`        | `str` \| `None`| Yes      | API key if required. |
| `host`           | `str` \| `None`| Yes      | Custom host endpoint. |
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
llm: ""
model: ""
aws_region_name: ""
aws_access_key: ""
aws_secret_key: ""
```


### JSON Example

```json
{
  "llm": "",
  "model": "",
  "aws_region_name": "",
  "aws_access_key": "",
  "aws_secret_key": ""
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
| `{footprints}` | `footprint.read: true` | The current contents of the shared footprint buffer at the time the node executes. |
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
          {footprints}                                    # reserved — footprint.read: true required
        user_input: |
          {user_message}                                  # reserved — prompt.user_message: true required

nodes:
  - id: "analyst"
    footprint:
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

## 5. `NodeFootprint`

Controls whether a node participates in the shared **footprint** document —
a persistent markdown buffer written and read across nodes during a single
`compile()` run.

| Field   | Type   | Optional | Description |
|---------|--------|----------|-------------|
| `read`  | `bool` | No (default `false`) | Inject the current footprint content into the node's prompt via the `{footprints}` placeholder. |
| `write` | `bool` | No (default `false`) | Append the node's LLM response to the footprint after execution. If the footprint originated from a file it is written back to disk after each write. |

### Node categories

Three behaviour patterns emerge from the `read`/`write` combination:

| Category | `read` | `write` | Role |
|----------|--------|---------|------|
| Cat-1 | `false` | `true`  | **Writer** — seeds the footprint (e.g. an assistant that drafts the initial content). |
| Cat-2 | `true`  | `true`  | **Enricher** — reads then extends the footprint (e.g. domain analysts). Multiple Cat-2 nodes run in parallel. |
| Cat-3 | `true`  | `false` | **Reader** — consumes the final footprint (e.g. a summarizer). |

The compiler infers the correct execution order automatically from these
categories even when the `edges` list is flat (no `children`/`fan_in`
declarations). Cat-1 nodes run first, Cat-2 nodes run in parallel after all
Cat-1 nodes complete, and Cat-3 nodes run after all Cat-2 nodes complete.

### Global `footprints` key

The top-level `footprints` key in the graph YAML configures the shared buffer:

```yaml
footprints: ./path/to/FOOTPRINT.md   # load initial content from a file (writes persist back)
# or
footprints: "# My Topic\n\n"          # inline markdown seed string
```

If `footprints` is omitted the buffer starts empty and writes are in-memory
only (no file persistence).

### YAML Example

```yaml
footprints: ./FOOTPRINT.md

nodes:
  - id: "assistant"
    footprint:
      read: false
      write: true   # Cat-1: seeds the footprint
    prompt:
      template: 0
      user_message: true

  - id: "analyst"
    footprint:
      read: true
      write: true   # Cat-2: enriches the footprint
    prompt:
      template: 1   # template uses {footprints}

  - id: "summarizer"
    footprint:
      read: true
      write: false  # Cat-3: consumes the final footprint
    prompt:
      template: 2   # template uses {footprints}
```

The `{footprints}` placeholder in a prompt template is automatically injected
when `footprint.read: true` is set on the node. No additional `prompt_placeholders`
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
| `footprint`         | `NodeFootprint` \| `None`    | Yes      | Footprint read/write participation. See §5 `NodeFootprint`. |
| `chat_history`      | `str` \| `None`              | Yes      | Reference to a chat history key (e.g. `"global"`). |
| `prompt`            | `NodePrompt` \| `None`       | Yes      | Prompt configuration. |
| `structured_output` | `dict[str, Any]` \| `None`   | Yes      | JSON schema for the node’s structured output. |
| `images`            | `list[int]` \| `None`        | Yes      | Indices of images to be provided to the node. |
| `documents`         | `list[int]` \| `None`        | Yes      | Indices of documents to be provided to the node. |
| `tools`             | `list[str]` \| `None`        | Yes      | Names of tools (matching the `name` field in the top-level `tools` list) available to this node. |
| `mcp_servers`       | `list[str]` \| `None`        | Yes      | IDs of MCP servers (matching the `id` field in the top-level `mcp_servers` list) available to this node. |


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

---

## 7. `GraphEdge`

| Field      | Type                       | Optional | Description |
|------------|----------------------------|----------|-------------|
| `node`     | `str`                      | No       | Unique identifier of the node this edge entry describes. |
| `children` | `list[GraphEdge]` \| `None`| Yes      | **Fan-out**: nodes to launch in parallel when this node completes. Each entry is itself a `GraphEdge`, allowing recursive sub-structure at any depth. |
| `fan_in`   | `list[GraphEdge]` \| `None`| Yes      | **Aggregation**: nodes this node waits for before starting. This node will not execute until every node listed here has completed. |

### Dependency semantics

**`edges` describe execution order only** — which node must complete before another can start. Data exchange between nodes is controlled independently by `message_passing` (`input`/`output`) on the nodes themselves.

**Two dependency patterns:**

- `children` (fan-out): node A completes → children B, C, D start in parallel.
- `fan_in` (aggregation): node E starts only when all nodes listed in its `fan_in` have completed.

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

## 8. `Graph`

| Field              | Type                                   | Optional | Description |
|--------------------|-----------------------------------------|----------|-------------|
| `models`           | `list[GraphModel]`                      | No       | List of LLM configurations. |
| `images`           | `list[GraphInputData]` \| `None`        | Yes      | Image sources used in the graph. |
| `documents`        | `list[GraphInputData]` \| `None`        | Yes      | Document sources used in the graph. |
| `tools`            | `list[LLMTool]` \| `None`               | Yes      | Tool definitions (from `kegal.llm.llm_model`). Each tool is referenced by its `name` in `GraphNode.tools`. |
| `prompts`          | `list[GraphInputData]`                  | No       | Prompt templates. |
| `chat_history`     | `dict[str, list[dict[str, str]]]` \| `None` | Yes   | Historical messages keyed by scope. |
| `user_message`     | `str` \| `None`                         | Yes      | Current user prompt. |
| `retrieved_chunks` | `str` \| `None`                         | Yes      | Additional retrieved content (e.g., document snippets). |
| `footprints`       | `str` \| `None`                         | Yes      | Path to a markdown file or an inline markdown string used as the shared footprint buffer. See §5 `NodeFootprint`. |
| `nodes`            | `list[GraphNode]`                       | No       | All nodes in the graph. |
| `edges`            | `list[GraphEdge]`                       | No       | Graph topology. |



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

## 9. `LLMTool` (from `kegal.llm.llm_model`)

| Field        | Type                                   | Optional | Description |
|--------------|-----------------------------------------|----------|-------------|
| `name`       | `str`                                  | No       | Name of the tool. |
| `description`| `str`                                  | No       | Short description of what the tool does. |
| `parameters` | `dict[str, LLMStructuredSchema]`       | No       | JSON-schema-style parameter definitions. |
| `required`   | `list[str]`                            | No       | List of required parameter names. |


> **Tip**: Use this model when you need to pass structured function‑call capabilities to the LLM.


## 10. `LLMStructuredSchema` (from `kegal.llm.llm_model`)

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




