# Documentation – KeGAL Internal Modules

This document covers the internal modules that power the KeGAL framework: the LLM abstraction layer (`kegal.llm.*`), the graph compiler (`kegal.compiler`), the prompt composer (`kegal.compose`), the utilities (`kegal.utils`), and the MCP handler (`kegal.mcp_handler`).

Most users never interact with these modules directly — the `Compiler` class is the public entry point. This reference is useful when extending the framework, writing custom LLM backends, or debugging graph execution.

> **Important** – Any secrets, AWS keys, or personal access tokens that appear in the example files have been replaced with an empty string (`""`) for safety.

## Table of Contents

- [1. `kegal.llm.__init__`](#1-kegalllm__init__)
- [2. `kegal.llm.llm_model`](#2-kegalllmllm_model)
- [3. `kegal.llm.llm_handler`](#3-kegalllmllm_handler)
- [4. `kegal.llm.llm_anthropic`](#4-kegalllmllm_anthropic)
- [5. `kegal.llm.llm_bedrock`](#5-kegalllmllm_bedrock)
- [6. `kegal.llm.llm_ollama`](#6-kegalllmllm_ollama)
- [7. `kegal.llm.llm_openai`](#7-kegalllmllm_openai)
- [8. `kegal.compiler`](#8-kegalcompiler)
- [9. `kegal.compose`](#9-kegalcompose)
- [10. `kegal.utils`](#10-kegalutils)
- [Example Configurations](#example-configurations)
- [11. `kegal.mcp_handler`](#11-kegalmcp_handler)

---

## 1. `kegal.llm.__init__`

The package’s `__init__` simply re‑exports the public LLM classes so they can be imported directly from `kegal.llm`.

```python
from kegal.llm import (
    LlmModel,
    LlmHandler,
    LlmAnthropic,
    LlmOpenai,
    LlmOllama,
    LlmBedrock,
)
```


---

## 2. `kegal.llm.llm_model`

This module defines the core **abstract base class** (`LlmModel`) and the Pydantic models that represent the data structures used throughout the framework.

### `LlmModel` (Abstract Base Class)

**Public methods**

| Method | Purpose |
|--------|---------|
| `complete(...)` | Main entry point for generating a response from an LLM. Returns an `LLMResponse` with the text output, token counts, and any tool calls. |
| `extract_format_from_media_type(media_type: str)` | Normalises a MIME type string (e.g. `"image/jpg"` → `"jpeg"`). |
| `extract_images_from_pdf(pdf: LLMPdfData)` | Extracts embedded images from a PDF and returns them as `LLMImageData` objects. |

**Abstract methods** (implemented by each concrete subclass — not called directly)

| Method | Purpose |
|--------|---------|
| `_chat_message(...)` | Convert a plain string into the provider-specific chat message format. |
| `_chat_history(...)` | Convert a list of `LLMMessage` objects into the provider-specific history format. |
| `_images_data(...)` | Convert `LLMImageData` objects into the provider-specific image payload. |
| `_pdfs_data(...)` | Convert `LLMPdfData` objects into the provider-specific document payload. |
| `_tools_data(...)` | Convert `LLMTool` objects into the provider-specific function-call schema. |
| `_structured_output_data(...)` | Convert an `LLMStructuredOutput` into the provider-specific schema constraint. |

> **Note** – You never call these methods directly. `complete()` assembles the full provider request internally. To add a new LLM backend, subclass `LlmModel` and implement the abstract methods above.

### Pydantic Models

#### `LLMImageData`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `media_type` | `str` | No | MIME type of the image (e.g. `"image/png"`). |
| `image_b64` | `str` | No | Base‑64 encoded image data. |

#### `LLMPdfData`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `doc_b64` | `str` | No | Base‑64 encoded PDF file. |

#### `LLMTool`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `name` | `str` | No | Name of the tool. |
| `description` | `str` | No | Short description. |
| `parameters` | `dict[str, LLMStructuredSchema]` | No | JSON‑schema‑style definitions of expected arguments. |
| `required` | `list[str]` | No | Required parameter names. |

#### `LLMStructuredSchema`

The most commonly used fields:

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `str` | Yes | JSON schema type (`"string"`, `"boolean"`, `"number"`, `"integer"`, `"object"`, `"array"`). |
| `enum` | `list[Any]` | Yes | Allowed literal values. |
| `description` | `str` | Yes | Human-readable description shown to the LLM. |
| `properties` | `dict[str, Any]` | Yes | For `"object"` types: nested field schemas. |
| `items` | `dict[str, Any]` | Yes | For `"array"` types: schema for each element. |
| `required` | `list[str]` | Yes | Required property names for objects. |

> The full schema supports all JSON Schema Draft 2020-12 keywords (min/max, pattern, allOf, anyOf, etc.). See [graph_doc.md §11 `LLMStructuredSchema`](graph_doc.md#11-llmstructuredschema-from-kegalllmllm_model) for the complete field reference.

#### `LLMStructuredOutput`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `json_output` | `LLMStructuredSchema` | No | The JSON schema the LLM must conform to in its response. |

#### `LLMMessage`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `role` | `str` | No | `"user"`, `"assistant"`, or `"system"`. |
| `content` | `str` | No | The text content of the message. |

---

## 3. `kegal.llm.llm_handler`

`LLMHandler` is the factory that selects and instantiates the correct concrete LLM backend based on the `llm` field in a `GraphModel` entry. The `Compiler` calls it once per model during initialisation; users never need to call it directly.

```python
class LLMHandler:
    def __init__(self, model_config: GraphModel) -> None
    def get_llm_instance(self) -> LlmModel
```

| Argument | Type | Description |
|----------|------|-------------|
| `model_config` | `GraphModel` | Configuration for a single LLM (model name, provider, credentials). |

`get_llm_instance()` reads `model_config.llm` and returns the matching subclass:

| `GraphModel.llm` value | Concrete class | Provider |
|---|---|---|
| `"anthropic"` | `LlmAnthropic` | Anthropic API (direct) |
| `"anthropic_aws"` | `LlmAnthropic` | Anthropic via AWS Bedrock inference profile |
| `"bedrock"` | `LlmBedrock` | Amazon Bedrock (native Bedrock models, e.g. Nova) |
| `"ollama"` | `LlmOllama` | Ollama local server |
| `"openai"` | `LlmOpenai` | OpenAI API |

---

## 4. `kegal.llm.llm_anthropic`

Concrete implementation for **Anthropic** (direct API via `llm: "anthropic"`, or Bedrock inference profile via `llm: "anthropic_aws"`). Instantiated automatically by `LLMHandler` — not created directly.

Key attributes set from `GraphModel`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Full model identifier (e.g., `"claude-sonnet-4-6"`) or Bedrock ARN. |
| `api_key` | `str` | Anthropic API key. Not required when using `anthropic_aws`. |

Advanced — calling `complete()` directly (the compiler handles this normally):

```python
instance = LLMHandler(model_config).get_llm_instance()
response = instance.complete(
    system_prompt="You are a helpful assistant.",
    user_message="Tell me about renewable energy.",
    chat_history=[],
    imgs_b64=None,
    pdfs_b64=None,
    tools_data=None,
    structured_output=None,
    temperature=0.7,
    max_tokens=1024,
)
```


---

## 5. `kegal.llm.llm_bedrock`

Concrete implementation for **Amazon Bedrock** native models (e.g. Amazon Nova) — use `llm: "bedrock"`. For Anthropic Claude via Bedrock, use `llm: "anthropic_aws"` instead. Instantiated automatically by `LLMHandler`.

Key attributes set from `GraphModel`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Bedrock model ARN or short name (e.g. `"amazon.nova-lite-v1:0"`). |
| `aws_region_name` | `str` | AWS region (e.g., `"eu-west-1"`). |
| `aws_access_key` | `str` | AWS access key ID. |
| `aws_secret_key` | `str` | AWS secret access key. |

---

## 6. `kegal.llm.llm_ollama`

Concrete implementation for **Ollama** (`llm: "ollama"`). Communicates with the local Ollama HTTP API — no external credentials required. Instantiated automatically by `LLMHandler`.

Key attributes set from `GraphModel`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Local model name (e.g., `"qwen2.5:7b"`). |
| `host` | `str` | Ollama server URL (default `"http://localhost:11434"`). |

---

## 7. `kegal.llm.llm_openai`

Concrete implementation for **OpenAI** (`llm: "openai"`). Uses the official `openai` Python client. Instantiated automatically by `LLMHandler`.

Key attributes set from `GraphModel`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | OpenAI model ID (e.g., `"gpt-4o-mini"`). |
| `api_key` | `str` | OpenAI API key. |

---

## 8. `kegal.compiler`

`compiler.py` contains the `Compiler` class that loads a graph configuration, initialises the LLM clients, and executes each node in the order defined by the graph edges.

### Usage

```python
from kegal import Compiler

compiler = Compiler(uri="path/to/graph.yml")
compiler.compile()
outputs = compiler.get_outputs()
```

### Compilation Flow

1. **Index validation** – `_validate_indices()` is called at construction time. It checks that every node's `model` index is within the `models` list and every `node.prompt.template` index is within the `prompts` list. All out-of-range references are collected and raised as a single `ValueError` before any LLM client is used.
2. **Prompt validation** – `_validate_prompts()` is called at construction time. It uses `string.Formatter().parse()` to extract every `{placeholder}` from all prompt templates and warns if a placeholder is referenced but not activated in the node config. Misconfigurations are reported before the first `compile()` call.
3. **DAG building** – `_build_dag()` resolves dependencies in four stages:
   - *Stage 1 (structural)*: the recursive edge tree is traversed; `children` creates fan-out dependencies (child waits for parent); `fan_in` creates aggregation dependencies (node waits for all listed nodes).
   - *Stage 2 (message passing)*: any node with `message_passing.output=true` becomes a dependency of all later nodes with `message_passing.input=true`, based on declaration order.
   - *Stage 3 (guard barrier)*: nodes whose `structured_output` contains a `validation` field automatically precede all other nodes.
   - *Stage 4 (blackboard)*: nodes are classified into Cat-1 (write-only), Cat-2 (read+write), Cat-3 (read-only) by their `blackboard` flags. Cat-2 nodes depend on all prior Cat-1 nodes; Cat-3 nodes depend on all prior Cat-1 and Cat-2 nodes. This infers the correct execution order with flat edge declarations.
4. **Topological scheduling** – `_topological_levels()` groups nodes into levels via [Kahn's algorithm](https://en.wikipedia.org/wiki/Topological_sorting). Nodes in the same level have no dependency on each other.
5. **Level execution** – for each level: guard nodes run sequentially first (graph aborts if any returns `validation: false`), then remaining nodes run in parallel via `ThreadPoolExecutor` if there is more than one. ReAct controllers run last within the level, after all regular nodes complete. Failures from parallel nodes are collected and re-raised as a `RuntimeError` after all futures complete.
6. **Message passing** – after each node, its output is written to `self.message_passing` if `output=true`; downstream nodes with `input=true` read from it.
7. **Blackboard update** – after each node with `blackboard.write=true`, its response is appended to the shared buffer (thread-safe). If the blackboard was loaded from a file, the file is written back immediately.

> **`compile()` is safe to call multiple times.** Each invocation resets `outputs` and `message_passing` before execution — results from previous runs are not carried over.

### Output Models

**`CompiledNodeOutput`** — result of a single node execution:

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | `str` | ID of the node. |
| `response` | `LLMResponse` | LLM response object (`messages`, `json_output`, `input_size`, `output_size`). |
| `compiled_time` | `float` | Wall-clock seconds this node took to execute. |
| `show` | `bool` | Whether to include this node in the markdown report. |
| `context_window` | `int \| None` | Token context window of the model used, if declared in `GraphModel.context_window`. |

**`CompiledOutput`** — aggregated result of the full graph:

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | `list[CompiledNodeOutput]` | All executed nodes in execution order. |
| `input_size` | `int` | Total input tokens consumed across all nodes. |
| `output_size` | `int` | Total output tokens produced across all nodes. |
| `compile_time` | `float` | Total wall-clock seconds for the full `compile()` call. |

### Serialisation

| Method | Description |
|--------|-------------|
| `get_outputs()` | Returns a `CompiledOutput` object. |
| `get_outputs_json(indent)` | Returns a JSON string. |
| `save_outputs_as_json(path)` | Writes the output to a JSON file. |
| `save_outputs_as_markdown(path)` | Writes a Markdown report. |

---

## 9. `kegal.compose`

`compose.py` contains prompt composition helpers used internally by the `Compiler` to assemble the final system and user prompts before each LLM call.

| Function | Description |
|----------|-------------|
| `compose_template_prompt(prompt_template)` | Convert a raw YAML template dict (with `system_template` and `prompt_template` sections) into a `{"system": str, "user": str}` dict. |
| `compose_node_prompt(prompt_template, placeholders, ...)` | Substitute `{placeholder}` tokens into the compiled template using `str.format()`. Raises a descriptive `KeyError` listing available placeholders if a token is missing. |
| `compose_images(data, indices)` | Build the `list[LLMImageData]` for a node from the graph-level image list. |
| `compose_documents(data, indices)` | Build the `list[LLMPdfData]` for a node from the graph-level document list. |
| `compose_tools(tools, names)` | Filter the graph-level `LLMTool` list to only those referenced by name in a node's `tools` field. |


---

## 10. `kegal.utils`

Utility functions used across the package:

| Function | Description |
|----------|-------------|
| `load_yml(source)` | Load a YAML file into a Python dict. |
| `load_json(source)` | Load a JSON file into a Python dict. |
| `load_contents(source)` | Load a YAML or JSON file based on extension. |
| `load_images_to_base64(source)` | Load an image from a path or URL and return `(media_type, base64_str)`. |
| `load_pdfs_to_base64(source)` | Load a PDF from a path or URL and return `(media_type, base64_str)`. |

### URI security — HTTPS only

All functions that accept a remote URI (`load_text_from_source`, `load_images_to_base64`, `load_pdfs_to_base64`) enforce an allowlist via `_check_uri_scheme()`. Only the `https` scheme is permitted; passing a `http://`, `file://`, `ftp://`, or any other scheme raises `ValueError` before any network call is made.

Local file paths (no scheme, or a relative path) are unaffected and continue to work as before.

```python
# Allowed
load_images_to_base64("https://example.com/diagram.png")
load_images_to_base64("/local/path/to/image.png")

# Raises ValueError — http is not in the allowlist
load_images_to_base64("http://internal-host/image.png")
```

To extend the allowlist (e.g., to re-enable `http` in a trusted private network), edit the `_ALLOWED_URI_SCHEMES` constant in `kegal/utils.py`.

---

## Example Configurations

Below are sanitized YAML/JSON snippets that illustrate how a `Graph` configuration can be written. Replace the empty string values with your own credentials when you deploy.

### Graph with an Anthropic Bedrock LLM and two prompt templates

**`rag_graph.yml`** (sanitized)

```yaml
models:
  - llm: "anthropic_aws"
    model: "arn:....claude-sonnet-4-5..."
    aws_region_name: "eu-west-1"
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

  - template:
      system_template:
        role_and_capabilities: |
          You are an expert research assistant specializing in renewable energy analysis.
          You maintain context from previous conversations and can reference earlier discussions.
          Your core capabilities include analyzing retrieved documents and providing evidence-based insights.
        behavioral_guidelines: |
          - Reference previous conversation context when relevant
          - Build upon earlier discussions naturally
          - Always base conclusions on retrieved information
          - Maintain consistency with previous statements
          - Be concise but comprehensive in your analysis
      prompt_template:
        context: |
          You have access to retrieved information that should inform your response.
          Consider both the conversation history and new retrieved data.
          Your analysis must be focused on {analysis_focus}.
        retrieved_contents: |
          Retrieved Information:
          {retrieved_chunks}
        instruction: |
          Given our previous discussion and the retrieved information above:
          {user_message}
          Please provide a comprehensive response that:
            - Builds on our previous conversation
            - Incorporates the new retrieved information
            - Addresses any gaps from earlier responses

chat_history:
  global:
    - role: "user"
      content: "What are the main renewable energy sources available today?"
    - role: "assistant"
      content: "The main renewable energy sources include solar, wind, hydroelectric, geothermal, and biomass energy. Each has unique advantages and applications depending on geographic and environmental factors."
    - role: "user"
      content: "Can you tell me more about the cost benefits of solar energy specifically?"
    - role: "assistant"
      content: "Solar energy costs have decreased significantly. Installation costs have dropped by about 40% over the past decade, making it increasingly competitive with traditional energy sources."

user_message: "What are the long‑term economic impacts of switching to renewable energy?"
retrieved_chunks: |
      Economic Report 2023: Renewable energy investments generated $1.8 trillion globally, creating 13.7 million jobs. Countries with higher renewable adoption show 15% lower energy costs over 10-year periods.
      Market Analysis: Solar and wind projects now offer the lowest cost electricity in most markets. Levelized cost of energy (LCOE) for utility‑scale solar fell to $0.048/kWh in 2023.   
      Industry Study: Renewable energy reduces price volatility compared to fossil fuels. Energy independence through renewables saves countries an average of $42 billion annually in imported fuel costs.

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

  - id: "test_rag_node"
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
      chat_history: "global"
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
      required: ["validation","cost_metrics", "growth_rate", "recommendation"]

edges:
  - node: "language_check"
  - node: "test_rag_node"
```


**JSON equivalent**

```json
{
  "models": [
    {
      "llm": "anthropic_aws",
      "model": "arn:aws:bedrock:eu-west-1:411096564688:inference-profile/eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "aws_region_name": "eu-west-1",
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
    },
    {
      "template": {
        "system_template": {
          "role_and_capabilities": "You are an expert research assistant specializing in renewable energy analysis.\nYou maintain context from previous conversations and can reference earlier discussions.\nYour core capabilities include analyzing retrieved documents and providing evidence-based insights.",
          "behavioral_guidelines": "- Reference previous conversation context when relevant\n- Build upon earlier discussions naturally\n- Always base conclusions on retrieved information\n- Maintain consistency with previous statements\n- Be concise but comprehensive in your analysis"
        },
        "prompt_template": {
          "context": "You have access to retrieved information that should inform your response.\nConsider both the conversation history and new retrieved data.\nYour analysis must be focused on {analysis_focus}.",
          "retrieved_contents": "Retrieved Information:\n{retrieved_chunks}",
          "instruction": "Given our previous discussion and the retrieved information above:\n{user_message}\nPlease provide a comprehensive response that:\n  - Builds on our previous conversation\n  - Incorporates the new retrieved information\n  - Addresses any gaps from earlier responses"
        }
      }
    }
  ],
  "chat_history": {
    "global": [
      { "role": "user", "content": "What are the main renewable energy sources available today?" },
      { "role": "assistant", "content": "The main renewable energy sources include solar, wind, hydroelectric, geothermal, and biomass energy. Each has unique advantages and applications depending on geographic and environmental factors." },
      { "role": "user", "content": "Can you tell me more about the cost benefits of solar energy specifically?" },
      { "role": "assistant", "content": "Solar energy costs have decreased significantly. Installation costs have dropped by about 40% over the past decade, making it increasingly competitive with traditional energy sources." }
    ]
  },
  "user_message": "What are the long‑term economic impacts of switching to renewable energy?",
  "retrieved_chunks": "Economic Report 2023: Renewable energy investments generated $1.8 trillion globally, creating 13.7 million jobs. Countries with higher renewable adoption show 15% lower energy costs over 10-year periods.\nMarket Analysis: Solar and wind projects now offer the lowest cost electricity in most markets. Levelized cost of energy (LCOE) for utility‑scale solar fell to $0.048/kWh in 2023.\nIndustry Study: Renewable energy reduces price volatility compared to fossil fuels. Energy independence through renewables saves countries an average of $42 billion annually in imported fuel costs.",
  "nodes": [
    {
      "id": "language_check",
      "model": 0,
      "temperature": 0.3,
      "max_tokens": 500,
      "show": true,
      "message_passing": { "input": false, "output": false },
      "prompt": { "template": 0, "user_message": true, "retrieved_chunks": false },
      "structured_output": {
        "description": "Language appropriateness assessment",
        "parameters": {
          "validation": { "type": "boolean", "description": "Whether message is appropriate for business use" },
          "action": { "type": "string", "description": "Action recommendation", "enum": ["approve", "reject"] }
        },
        "required": ["validation", "action"]
      }
    },
    {
      "id": "test_rag_node",
      "model": 0,
      "temperature": 0.7,
      "max_tokens": 1000,
      "show": true,
      "message_passing": { "input": false, "output": false },
      "prompt": { "template": 1, "user_message": true, "retrieved_chunks": true, "chat_history": "global", "prompt_placeholders": { "analysis_focus": "economic benefits" } },
      "structured_output": {
        "description": "Renewable energy analysis summary",
        "parameters": {
          "validation": { "type": "boolean", "description": "Whether the message is consistent with the context or not" },
          "cost_metrics": { "type": "object", "description": "Cost analysis" },
          "growth_rate": { "type": "number", "description": "Annual growth percentage" },
          "recommendation": { "type": "string", "description": "Key recommendation", "enum": ["invest", "wait", "diversify"] }
        },
        "required": ["validation", "cost_metrics", "growth_rate", "recommendation"]
      }
    }
  ],
  "edges": [
    { "node": "language_check" },
    { "node": "test_rag_node" }
  ]
}
```



---

## 11. `kegal.mcp_handler`

`McpHandler` connects a single MCP server (stdio or SSE transport), lists its tools, and executes tool calls on behalf of the compiler. The LLM layer never communicates with MCP directly — it only sees translated `LLMTool` definitions and receives plain-string results.

The async MCP session runs on a dedicated background thread with its own event loop. The entire session lifetime — connect, tool calls, disconnect — executes within a single async task, so anyio cancel scopes are always entered and exited from the same task. The synchronous compiler calls `connect`, `call_tool`, and `close` without managing coroutines directly.

### Constructor

```python
McpHandler(server: GraphMcpServer, call_timeout: float = 60)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server` | `GraphMcpServer` | — | Server configuration loaded from the graph YAML. |
| `call_timeout` | `float` | `60` | Per-call timeout in seconds. Each `call_tool()` invocation blocks for at most this duration; raises `concurrent.futures.TimeoutError` if the MCP server does not respond in time. |

### Public API

| Method | Description |
|--------|-------------|
| `connect()` | Open the MCP session and load available tools. |
| `disconnect()` | Close the MCP session and stop the background event loop. Called internally by `Compiler.close()`. |
| `list_tools() -> list[LLMTool]` | Return all tools exposed by the server as `LLMTool` objects. |
| `tool_names() -> set[str]` | Return the set of tool names available on this server. |
| `call_tool(name, arguments) -> str` | Execute a tool call and return the result as a plain string. Raises `TimeoutError` if `call_timeout` is exceeded. |

### YAML configuration (`GraphMcpServer`)

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `id` | `str` | No | Unique identifier for this MCP server. Referenced by name in `mcp_servers` on nodes. |
| `transport` | `"stdio"` \| `"sse"` | No | Connection transport. |
| `command` | `str` \| `None` | stdio only | Executable to launch (e.g. `"python"`). |
| `args` | `list[str]` \| `None` | stdio only | Arguments passed to the command. |
| `env` | `dict[str, str]` \| `None` | stdio only | Extra environment variables for the subprocess. |
| `url` | `str` \| `None` | SSE only | HTTP endpoint of the SSE MCP server. |

### YAML Example

```yaml
mcp_servers:
  - id: "sqlite_server"
    transport: "stdio"
    command: "python"
    args: ["path/to/mcp_server.py"]

nodes:
  - id: "analyst"
    mcp_servers: ["sqlite_server"]   # references the server by its id
    message_passing:
      input: false
      output: true
    ...

edges:
  - node: "analyst"
```

> **Note**: Multiple nodes can reference the same MCP server. Tool calls from parallel nodes on the same server are safely queued on the server's event loop, but effective throughput is serialized per server.

---

> For runtime usage and worked examples refer to [README.md](../README.md) and [tutorials.md](tutorials.md).