# Tutorial 10: Multi-Provider Graphs

Different nodes in the same graph can use different LLM providers and models.
Declare every model you need in the top-level `models:` list and reference
them by index on each node. This lets you use the right model for each task —
a fast, cheap model for classification and a powerful one for generation.

---

## 1. Basic: two providers in one graph

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."

prompts:
  - template:  # 0 — fast pre-check (Ollama)
      system_template:
        role: |
          Classify this support ticket as one of:
          billing, technical, general.
          Return one word only.
      prompt_template:
        message: "{user_message}"

  - template:  # 1 — detailed analysis (Anthropic)
      system_template:
        role: |
          You are a senior support engineer. Write a detailed,
          actionable response to this support ticket.
      prompt_template:
        ticket: "{user_message}"

nodes:
  - id: "classifier"
    model: 0             # Ollama — fast and cheap
    temperature: 0.0
    max_tokens: 16
    show: false
    message_passing: { output: true }
    prompt: { template: 0, user_message: true }

  - id: "responder"
    model: 1             # Anthropic — better quality for the customer-facing reply
    temperature: 0.4
    max_tokens: 512
    show: true
    message_passing: { input: true }
    prompt: { template: 1, user_message: true }

edges:
  - node: "classifier"
  - node: "responder"
```

```python
from kegal import Compiler

with Compiler(uri="multi_provider.yml") as compiler:
    compiler.user_message = "My invoice shows the wrong amount."
    compiler.compile()
```

---

## 2. Intermediate: fast guard + powerful analysis

Use a lightweight model to validate the input (a task that requires very
little reasoning) and reserve the powerful model for the main response.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"      # small, fast
    host: "http://localhost:11434"
  - llm: "anthropic"
    model: "claude-opus-4-7"  # large, capable
    api_key: "sk-ant-..."

nodes:
  - id: "input_guard"
    model: 0                   # small model is sufficient for boolean classification
    temperature: 0.0
    max_tokens: 64
    show: false
    prompt:
      template: 0
      user_message: true
    structured_output:
      description: "Input safety check"
      parameters:
        validation:
          type: "boolean"
      required: ["validation"]

  - id: "main_analyst"
    model: 1                   # large model for the substantive response
    temperature: 0.5
    max_tokens: 2048
    show: true
    prompt:
      template: 1
      user_message: true
      retrieved_chunks: true

edges:
  - node: "input_guard"
  - node: "main_analyst"
```

---

## 3. Intermediate: parallel specialists on different providers

Fan out to multiple specialist nodes, each using the best model for its task.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
  - llm: "ollama"
    model: "qwen2.5-vl:7b"        # vision-capable for image analysis
    host: "http://localhost:11434"
  - llm: "anthropic"
    model: "claude-sonnet-4-6"    # strongest for the final synthesis
    api_key: "sk-ant-..."

images:
  - uri: "./assets/chart.png"

nodes:
  - id: "text_analyst"
    model: 0                       # text-only model for reading the report
    ...
    prompt: { template: 0, user_message: true, retrieved_chunks: true }

  - id: "image_analyst"
    model: 1                       # vision model for the chart
    ...
    images: [0]
    prompt: { template: 1 }

  - id: "synthesizer"
    model: 2                       # most capable for final synthesis
    ...
    message_passing: { input: true }
    prompt: { template: 2 }

edges:
  - node: "synthesizer"
    fan_in:
      - node: "text_analyst"
      - node: "image_analyst"
```

---

## 4. Advanced: mixing cloud and local models

Combine Anthropic or OpenAI cloud models with locally-run Ollama models to
balance capability, latency, and cost.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    # local — no API key, no network latency, free

  - llm: "openai"
    model: "gpt-4o-mini"
    api_key: "sk-..."
    # cloud — small but capable, low cost

  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."
    # cloud — strongest reasoning

nodes:
  - id: "pre_filter"
    model: 0       # local Ollama — zero cost for simple filtering
    ...

  - id: "extractor"
    model: 1       # OpenAI mini — structured extraction, low cost
    ...

  - id: "reasoning"
    model: 2       # Anthropic — complex reasoning step
    ...
```

---

## 5. Provider reference

| Provider key       | Required fields              | Notes |
|--------------------|------------------------------|-------|
| `ollama`           | `host`                       | Local or remote Ollama instance. |
| `anthropic`        | `api_key`                    | Anthropic cloud API. |
| `anthropic_aws`    | `api_key`                    | Anthropic via AWS API Gateway. |
| `openai`           | `api_key`                    | OpenAI cloud API. |
| `bedrock`          | `aws_region_name`, `aws_access_key`, `aws_secret_key` | AWS Bedrock. |

```yaml
# Ollama
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    context_window: 32768

# Anthropic
models:
  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."

# OpenAI
models:
  - llm: "openai"
    model: "gpt-4o"
    api_key: "sk-..."

# AWS Bedrock
models:
  - llm: "bedrock"
    model: "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    aws_region_name: "us-east-1"
    aws_access_key: "AKIA..."
    aws_secret_key: "..."
```

---

## 6. Advanced: `context_window` per model

Declare `context_window` on any model where you need accurate ReAct
compaction or utilization reporting. The value is specific to each model
instance in the `models:` list.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    context_window: 32768     # 32 K tokens

  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."
    context_window: 200000    # 200 K tokens
```

See [Tutorial 13: Context window](13_context_window.md) for how this is used.

---

## Key points

- Each entry in `models:` is a fully independent LLM configuration.
  The same provider can appear multiple times with different models or hosts.
- Nodes reference models by **index** — the first model in the list is `0`.
- All models are instantiated at `Compiler` construction. If a provider fails
  to connect, the error surfaces before the first `compile()` call.
- `context_window` is optional but enables accurate ReAct compaction and
  per-node utilization display.

---

> **Related tutorials:**
> [13 Context window](13_context_window.md) — tracking token usage per model  
> [03 Guard nodes](03_guard_nodes.md) — using a fast model as a guard before a powerful one  
> [12 ReAct loop](12_react_loop.md) — controller and agents can use different models
