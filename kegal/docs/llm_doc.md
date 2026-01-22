# Documentation – `kegal.llm` Framework

The **`kegal.llm`** package implements a small, extensible LLM abstraction layer that powers the `Graph` system.  
Below is a high‑level overview of each module in the package, the public API they expose, and concrete YAML/JSON examples that can be used as a starting point for your own graph definitions.

> **Important** – Any secrets, AWS keys, or personal access tokens that appear in the original example files have been replaced with an empty string (`""`) for safety.

> The documentation follows the same style as the existing `graph_doc.md`.  Wherever a data model is used, we provide a table that lists fields, types, optionality, and a short description.  YAML and JSON snippets are also included for quick reference.

---

## 1. `kegal.llm.__init__`

The package’s `__init__` simply re‑exports the public LLM classes so they can be imported directly from `kegal.llm`.

```python
# kegal/llm/__init__.py
__all__ = [
    "LLMHandler",
    "LLMImageData",
    "LLMPdfData",
    "LLMTool",
    "LLMStructuredOutput",
    "LLMStructuredSchema",
    "LLMMessage",
]
```


---

## 2. `kegal.llm.llm_model`

This module defines the core **abstract base class** (`LlmModel`) and the Pydantic models that represent the data structures used throughout the framework.

### `LlmModel` (Abstract Base Class)

| Method | Purpose |
|--------|---------|
| `complete(...)` | Main entry point for generating a response from an LLM. |
| `_chat_message(...)` | Convert a plain string into the LLM‑specific chat message format. |
| `_chat_history(...)` | Convert a history of messages into the LLM‑specific format. |
| `_images_data(...)` | Convert images into the LLM‑specific data payload. |
| `_pdfs_data(...)` | Convert PDFs into the LLM‑specific data payload. |
| `_tools_data(...)` | Convert a list of `LLMTool` objects into the LLM‑specific function‑call payload. |
| `_structured_output_data(...)` | Convert a `LLMStructuredOutput` into the LLM‑specific schema. |
| `extract_format_from_media_type(media_type: str)` | Normalises a MIME type (e.g. `image/jpg` → `jpeg`). |
| `extract_images_from_pdf(pdf: LLMPdfData)` | Extracts embedded images from a PDF. |
| `_is_json(...)` | Helper to validate JSON strings. |

> **Note** – Concrete LLM classes (Anthropic, Bedrock, OpenAI, Ollama) implement the abstract methods.

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

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `type` | `str` | No | JSON schema type. |
| `enum` | `list[Any]` | Yes | Allowed values (if any). |
| `description` | `str` | Yes | Human readable description. |
| `properties` | `dict[str, Any]` | Yes | For `"object"` types: nested schema. |
| `items` | `dict[str, Any]` | Yes | For `"array"` types: element schema. |
| `required` | `list[str]` | Yes | Required properties for objects. |

#### `LLMStructuredOutput`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `description` | `str` | No | Brief description of the output. |
| `parameters` | `dict[str, LLMStructuredSchema]` | No | JSON schema of the expected output. |
| `required` | `list[str]` | No | Required parameter names. |

#### `LLMMessage`

| Field | Type | Optional | Description |
|-------|------|----------|-------------|
| `role` | `str` | No | `"user"`, `"assistant"`, or `"system"`. |
| `content` | `str` | No | The text content of the message. |

---

## 3. `kegal.llm.llm_handler`

`LLMHandler` is the factory and dispatcher that selects the appropriate concrete LLM implementation based on the configuration in a `Graph` node.

```python
class LLMHandler:
    def __init__(self, model_config: GraphModel) -> None
    def get_llm_instance(self) -> LlmModel
```


| Argument | Type | Description |
|----------|------|-------------|
| `model_config` | `GraphModel` | Configuration for a single LLM (model name, provider, credentials). |

`LLMHandler.get_llm_instance()` returns an instance of a subclass of `LlmModel` that can be used to call `complete(...)`.

---

## 4. `kegal.llm.llm_anthropic`

Concrete implementation for **Anthropic** (via the official client or the Anthropic API wrapper).  
The class inherits from `LlmModel` and implements all abstract methods.

Key attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Full model identifier (e.g., `"claude-3-5-sonnet-20240620"`). |
| `api_key` | `str` | Anthropic API key (empty string in public docs). |

Typical usage:

```python
anthropic = LLMHandler(model_config).get_llm_instance()
response = anthropic.complete(
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

Concrete implementation for **Amazon Bedrock**.  
It handles the conversion of LLM data structures to the Bedrock API payload and vice‑versa.

Key attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Bedrock model ARN or short name. |
| `aws_region_name` | `str` | AWS region (e.g., `"eu-west-1"`). |
| `aws_access_key` | `str` | AWS access key ID (empty string in public docs). |
| `aws_secret_key` | `str` | AWS secret access key (empty string in public docs). |

---

## 6. `kegal.llm.llm_ollama`

Concrete implementation for **Ollama** (local LLM host).  
No external credentials are required; it communicates with the local HTTP API.

Key attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Local model name (e.g., `"llama3.2"`). |

---

## 7. `kegal.llm.llm_openai`

Concrete implementation for **OpenAI** (ChatGPT, GPT‑4, etc.).  
Uses the official `openai` Python client.

Key attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `model` | `str` | OpenAI model ID (e.g., `"gpt-4o-mini"`). |
| `api_key` | `str` | OpenAI API key (empty string in public docs). |

---

## 8. `kegal.compiler`

`compiler.py` contains a helper that transforms a `Graph` instance into a serialized representation that can be executed by the engine.  
Key function:

```python
def compile_graph(graph: Graph) -> CompiledGraph:
    """Compile a `Graph` object into an executable representation."""
```


The compiled output is a lightweight Python module or a dictionary that can be imported and executed.

---

## 9. `kegal.compose`

`compose.py` provides a small DSL to build a `Graph` programmatically.  
Typical usage:

```python
from kegal.graph import Graph, GraphNode, GraphEdge

graph = Graph(
    models=[...],
    prompts=[...],
    nodes=[
        GraphNode(
            id="node1",
            model=0,
            temperature=0.5,
            max_tokens=512,
            show=True,
            message_passing=NodeMessagePassing(input=True, output=True),
            prompt=NodePrompt(template=0, user_message=True, retrieved_chunks=False),
        ),
    ],
    edges=[
        GraphEdge(node="node1", children=[1]),
    ],
)
```


---

## 10. `kegal.utils`

Utility functions used across the package:

| Function | Description |
|----------|-------------|
| `load_yaml(path: str) -> dict` | Load a YAML file into a Python dict. |
| `to_json(obj: Any) -> str` | Serialize an object to JSON. |
| `base64_encode(file_path: str) -> str` | Return a base64 string for a file. |
| `extract_text_from_pdf(pdf_bytes: bytes) -> str` | Simple OCR/strip text from PDF. |

---

# Example Configurations

Below are sanitized YAML/JSON snippets that illustrate how a `Graph` configuration can be written.  
Replace the empty string values with your own credentials when you deploy.

## 1. Graph with an Anthropic Bedrock LLM and two prompt templates

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
    children: null
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
    { "node": "language_check", "children": null },
    { "node": "test_rag_node", "children": null }
  ]
}
```



---

# Quick Start

```shell script
# 1. Install the package dependencies
pip install -r requirements.txt

# 2. Create a YAML configuration (e.g. rag_graph.yml) using the templates above.
#    Remember to set the correct credentials for your environment.

# 3. Run the graph compiler
python -m kegal.compiler rag_graph.yml

# 4. Execute the compiled graph (the compiler will produce a Python module that can be imported)
python -m kegal.execute compiled_graph.py
```


> For detailed runtime usage, refer to the `README.md` in the root of the repository.

---