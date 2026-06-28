# Batch Inference

Batch inference lets KeGAL submit multiple LLM calls in a single asynchronous job instead of making them one by one in real time. Most providers offer a ~50% cost reduction for batch jobs and have no rate-limit pressure on throughput.

KeGAL exposes batch inference at **two independent levels**, both controlled entirely from the YAML graph file.

---

## Provider Support

| Provider | Batch API | Cost reduction | Tools | Structured output |
|---|---|---|---|---|
| `anthropic` | `client.messages.batches.create()` | ~50% | Yes | Yes |
| `anthropic_aws` | Same as `anthropic` | ~50% | Yes | Yes |
| `openai` | JSONL upload + `client.batches.create()` | ~50% | Yes | Yes |
| `gemini` | `client.batches.create()` | ~50% | Yes | Yes |
| `bedrock` | `CreateModelInvocationJob` (S3 + IAM) | ~50% | No | No |
| `ollama` | None — uses thread pool over `complete()` | None | Yes | Yes |

Bedrock batch does not support tools or structured output. Declaring a batch node that uses those features with a Bedrock model raises `ValueError` at `Compiler()` construction.

Ollama has no native batch API. When a batch mode is activated on an Ollama node, KeGAL falls back to a `ThreadPoolExecutor` that calls `complete()` concurrently, providing parallelism without a batch queue.

---

## Level 1: Intra-node Batch (`batch_user_messages`)

**Semantic:** one node, one prompt template, one model — N calls, one per user message. All N calls share the same system prompt, tools, and node configuration. The provider's native async batch API submits all N requests in a single job.

### New fields

**On `Graph` (top level):**

| Field | Type | Description |
|---|---|---|
| `batch_user_messages` | `list[str]` | List of user messages to process. Mutually exclusive with `user_message`. |

**On `NodePrompt`:**

| Field | Type | Description |
|---|---|---|
| `batch_use_messages` | `list[int]` | Indices into `batch_user_messages` this node processes. |

**On `GraphNode`:**

| Field | Type | Description |
|---|---|---|
| `batch_message_passing` | `NodeBatchMessagePassing` | Controls how the N batch outputs flow to downstream nodes. |

`NodeBatchMessagePassing` has two boolean flags, both defaulting to `false`:

| Flag | Meaning |
|---|---|
| `output: true` | The N outputs are collected after the batch job completes and forwarded downstream as individual items. |
| `input: true` | This node receives each upstream batch item as a separate call (N calls, one per item). |

### Constraint

`batch_message_passing.output` and `batch_message_passing.input` must be declared on both the producing node and the consuming node respectively. If the producing node has `output: true` but the downstream node does not have `input: true`, `ValueError` is raised at `Compiler()` construction.

### Output format

How the N results reach the downstream node depends on which `message_passing` variant is used on the producing node:

#### With `message_passing.output: true` (tagged format)

The N results are concatenated into a single string using `<message_N>` XML tags and passed to the downstream node as the `{message_passing}` placeholder in a single LLM call:

**Text output:**
```
<message_0>text result for message 0</message_0>
<message_1>text result for message 1</message_1>
<message_2>text result for message 2</message_2>
```

**Structured output** (each object serialised with `json.dumps`):
```
<message_0>{"field": "value_0"}</message_0>
<message_1>{"field": "value_1"}</message_1>
<message_2>{"field": "value_2"}</message_2>
```

#### With `batch_message_passing.output: true` (pass-through format)

Each item is passed to the downstream node individually, identical to how a regular non-batch node passes its output. The downstream node is called N times, once per item. This is transparent to the downstream node: it sees a normal single-item input on each call.

### YAML Example

```yaml
batch_user_messages:
  - "Analyse the financial performance of company A."
  - "Analyse the financial performance of company B."
  - "Analyse the financial performance of company C."

models:
  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "${ANTHROPIC_API_KEY}"

prompts:
  # 0 — analyst: one call per company
  - template:
      system_template:
        role: |
          You are a financial analyst. Produce a concise summary of the company's
          financial performance covering revenue, margin, and key risks.
      prompt_template:
        task: "{user_message}"

  # 1 — synthesiser: receives all three summaries
  - template:
      system_template:
        role: |
          You are a portfolio strategist. Given the individual company analyses below,
          produce a comparative overview and investment recommendation.
      prompt_template:
        analyses: |
          {message_passing}

nodes:
  - id: "analyst"
    model: 0
    temperature: 0.3
    max_tokens: 512
    show: true
    prompt:
      template: 0
      batch_use_messages: [0, 1, 2]   # process all three user messages
    message_passing:
      output: true                     # tagged <message_N> format to synthesiser

  - id: "synthesiser"
    model: 0
    temperature: 0.5
    max_tokens: 1024
    show: true
    message_passing:
      input: true                      # receives <message_0>, <message_1>, <message_2>
    prompt:
      template: 1

edges:
  - node: "analyst"
  - node: "synthesiser"
```

### Batch envelope in outputs

When a node runs in batch mode, `CompiledNodeOutput.response` contains a batch envelope for developer inspection:

```json
{
  "messages": ["summary of company A", "summary of company B", "summary of company C"],
  "batch_size": 3
}
```

For structured output nodes:
```json
{
  "messages": [{"revenue": "...", "margin": "..."}, {"revenue": "...", "margin": "..."}, {"revenue": "...", "margin": "..."}],
  "batch_size": 3
}
```

This envelope is for `get_outputs()` inspection only. It is never sent to a downstream LLM as-is.

---

## Level 2: Inter-node Batch (`batch_children` / `batch_fan_in`)

**Semantic:** N separate nodes, each with its own prompt and model, submitted together as one batch API job. Functionally equivalent to `children` / `fan_in`, but the N requests go to the provider in a single batch job rather than as concurrent real-time calls.

All nodes in a `batch_children` or `batch_fan_in` group must reference the same model index. Using different model indices raises `ValueError` at `Compiler()` construction.

### New edge fields

| Field | Type | Description |
|---|---|---|
| `batch_children` | `list[GraphEdge]` | Nodes to submit as a single batch job when this node completes. Mutually exclusive with `children` and `ordered_children`. |
| `batch_fan_in` | `list[GraphEdge]` | Nodes this node waits for, submitted as a single batch job. Mutually exclusive with `fan_in` and `ordered_fan_in`. |

### YAML Example

```yaml
models:
  - llm: "anthropic"
    model: "claude-haiku-4-5-20251001"
    api_key: "${ANTHROPIC_API_KEY}"

prompts:
  - template:    # 0 — dispatcher
      system_template:
        role: Identify the top three research sub-questions from the user's query.
      prompt_template:
        query: "{user_message}"

  - template:    # 1 — branch analyst (reused by all three branches)
      system_template:
        role: Research this specific sub-question in depth.
      prompt_template:
        question: "{message_passing}"

  - template:    # 2 — synthesiser
      system_template:
        role: Combine the three research findings into a coherent report.
      prompt_template:
        findings: "{message_passing}"

nodes:
  - id: "dispatcher"
    model: 0
    temperature: 0.2
    max_tokens: 256
    show: false
    prompt: { template: 0, user_message: true }
    message_passing: { output: true }

  - id: "branch_1"
    model: 0
    temperature: 0.5
    max_tokens: 512
    show: true
    prompt: { template: 1 }
    message_passing: { input: true, output: true }

  - id: "branch_2"
    model: 0
    temperature: 0.5
    max_tokens: 512
    show: true
    prompt: { template: 1 }
    message_passing: { input: true, output: true }

  - id: "branch_3"
    model: 0
    temperature: 0.5
    max_tokens: 512
    show: true
    prompt: { template: 1 }
    message_passing: { input: true, output: true }

  - id: "synthesiser"
    model: 0
    temperature: 0.5
    max_tokens: 1024
    show: true
    prompt: { template: 2 }
    message_passing: { input: true }

edges:
  - node: "dispatcher"
    batch_children:              # submit branch_1, branch_2, branch_3 as one batch job
      - node: "branch_1"
      - node: "branch_2"
      - node: "branch_3"

  - node: "synthesiser"
    batch_fan_in:                # wait for all three; they were submitted as a batch
      - node: "branch_1"
      - node: "branch_2"
      - node: "branch_3"
```

---

## AWS Bedrock: extra model configuration

Bedrock batch requires an S3 bucket for input/output files and an IAM role with the appropriate permissions. Add three fields to the model entry:

```yaml
models:
  - llm: "bedrock"
    model: "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0"
    aws_region_name: "${AWS_REGION}"
    aws_access_key: "${AWS_ACCESS_KEY_ID}"
    aws_secret_key: "${AWS_SECRET_ACCESS_KEY}"
    batch_role_arn: "${BEDROCK_BATCH_ROLE_ARN}"
    batch_s3_input_uri: "s3://my-bucket/kegal/input"
    batch_s3_output_uri: "s3://my-bucket/kegal/output"
```

| Field | Type | Description |
|---|---|---|
| `batch_role_arn` | `str` | ARN of the IAM role Bedrock assumes to read/write S3. |
| `batch_s3_input_uri` | `str` | S3 prefix where KeGAL writes the JSONL input file. |
| `batch_s3_output_uri` | `str` | S3 prefix where Bedrock writes results. |

If any of the three fields are absent when a batch mode is activated on a Bedrock node, `ValueError` is raised at `Compiler()` construction, listing the missing fields.

---

## Mutual exclusivity rules

| Field | Exclusive with |
|---|---|
| `batch_user_messages` | `user_message` |
| `batch_children` | `children`, `ordered_children` |
| `batch_fan_in` | `fan_in`, `ordered_fan_in` |

---

## Out of scope for v1

- ReAct controller nodes inside batch graphs (`ValueError` at construction)
- Streaming partial results during batch polling
- Mixed model indices in a single `batch_children` / `batch_fan_in` group
- Bedrock batch with tools or structured output
