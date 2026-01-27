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

## 4. `NodeMessagePassing`

| Field    | Type  | Optional | Description                                        |
|----------|-------|----------|----------------------------------------------------|
| `input`  | `bool`| No       | Flag to forward input to the node.                 |
| `output` | `bool`| No       | Flag to expose the node’s output to downstream nodes. |


### YAML Example

```yaml
input: false
output: false
```


### JSON Example

```json
{
  "input": false,
  "output": false
}
```


---

## 5. `GraphNode`

| Field               | Type                         | Optional | Description |
|---------------------|------------------------------|----------|-------------|
| `id`                | `str`                        | No       | Unique identifier of the node. |
| `model`             | `int`                        | No       | Index of the model in the global `models` list. |
| `temperature`       | `float`                      | No       | Sampling temperature for the LLM. |
| `max_tokens`        | `int`                        | No       | Maximum token length for the LLM response. |
| `show`              | `bool`                       | No       | Whether the node is visible in visualisations. |
| `message_passing`   | `NodeMessagePassing`         | No       | Configuration of input/output passing. |
| `chat_history`      | `str` \| `None`              | Yes      | Reference to a chat history key (e.g. `"global"`). |
| `prompt`            | `NodePrompt` \| `None`       | Yes      | Prompt configuration. |
| `structured_output` | `dict[str, Any]` \| `None`   | Yes      | JSON schema for the node’s structured output. |
| `images`            | `list[int]` \| `None`        | Yes      | Indices of images to be provided to the node. |
| `documents`         | `list[int]` \| `None`        | Yes      | Indices of documents to be provided to the node. |
| `tools`             | `list[int]` \| `None`        | Yes      | Indices of tools to be provided to the node. |


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

## 6. `GraphEdge`

| Field      | Type            | Optional | Description                                                   |
|------------|-----------------|----------|---------------------------------------------------------------|
| `node`     | `str`           | No       | Identifier of the node that this edge originates from.       |
| `children` | `list[int]` \| `None` | Yes      | Indices of child nodes; `null` indicates no children. |

### YAML Example

```yaml
node: "language_check"
children: null
```


### JSON Example

```json
{
  "node": "language_check",
  "children": null
}
```


---

## 7. `Graph`

| Field              | Type                                   | Optional | Description |
|--------------------|-----------------------------------------|----------|-------------|
| `models`           | `list[GraphModel]`                      | No       | List of LLM configurations. |
| `images`           | `list[GraphInputData]` \| `None`        | Yes      | Image sources used in the graph. |
| `documents`        | `list[GraphInputData]` \| `None`        | Yes      | Document sources used in the graph. |
| `tools`            | `list[LLMTool]` \| `None`               | Yes      | Tool definitions (from `kegal.llm.llm_model`). |
| `prompts`          | `list[GraphInputData]`                  | No       | Prompt templates. |
| `chat_history`     | `dict[str, list[dict[str, str]]]` \| `None` | Yes   | Historical messages keyed by scope. |
| `user_message`     | `str` \| `None`                         | Yes      | Current user prompt. |
| `retrieved_chunks` | `str` \| `None`                         | Yes      | Additional retrieved content (e.g., document snippets). |
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
    children: null
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
      "node": "language_check",
      "children": null
    }
  ]
}
```


---

## 8. `LLMTool` (from `kegal.llm.llm_model`)

| Field        | Type                                   | Optional | Description |
|--------------|-----------------------------------------|----------|-------------|
| `name`       | `str`                                  | No       | Name of the tool. |
| `description`| `str`                                  | No       | Short description of what the tool does. |
| `parameters` | `dict[str, LLMStructuredSchema]`       | No       | JSON-schema-style parameter definitions. |
| `required`   | `list[str]`                            | No       | List of required parameter names. |


> **Tip**: Use this model when you need to pass structured function‑call capabilities to the LLM.


## 9. `LLMStructuredSchema` (from `kegal.llm.llm_model`)

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




