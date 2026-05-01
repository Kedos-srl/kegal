# Tutorial 13: Context Window Tracking and Saving Outputs

KeGAL tracks token usage per node and can display context utilization when
the model's capacity is declared. This tutorial also covers the three output
serialization methods available after `compile()`.

---

## 1. Basic: declaring `context_window`

Add `context_window` (in tokens) to a model entry. This unlocks:

1. **Accurate ReAct compaction** — the resume threshold is computed against
   the true context window instead of `max_tokens` (the output budget).
2. **Context utilization in markdown output** — `save_outputs_as_markdown()`
   prints a utilization percentage per node.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    context_window: 32768     # 32 K token context window
```

```python
from kegal import Compiler

with Compiler(uri="graph.yml") as compiler:
    compiler.user_message = "Explain quantum entanglement."
    compiler.compile()

    outputs = compiler.get_outputs()
    for node in outputs.nodes:
        if node.context_window:
            used  = node.response.input_size
            total = node.context_window
            print(f"[{node.node_id}] {used}/{total} ({used/total*100:.1f}%)")
```

---

## 2. Intermediate: accessing output data

Three serialization methods are available after `compile()`:

| Method | Description |
|---|---|
| `get_outputs()` | Returns a `CompiledOutput` object for programmatic access. |
| `save_outputs_as_json(path)` | Writes full output to a JSON file. |
| `save_outputs_as_markdown(path)` | Writes a human-readable Markdown report. |

### `get_outputs()` — programmatic access

```python
outputs = compiler.get_outputs()

print(f"Total time  : {outputs.compile_time:.2f}s")
print(f"Input tokens: {outputs.input_size}")
print(f"Output tokens: {outputs.output_size}")

for node in outputs.nodes:
    print(f"\n[{node.node_id}] ({node.compiled_time:.2f}s)")
    print(f"  input={node.response.input_size}  output={node.response.output_size}")

    if node.response.messages:
        for msg in node.response.messages:
            print(f"  {msg}")

    if node.response.json_output:
        print(f"  JSON: {node.response.json_output}")

    if node.context_window:
        pct = node.response.input_size / node.context_window * 100
        print(f"  Context: {node.response.input_size}/{node.context_window} ({pct:.1f}%)")
```

### `save_outputs_as_json(path)` — persist raw data

```python
compiler.save_outputs_as_json("outputs/run_output.json")
```

The JSON file contains all nodes with their token counts, timings, messages,
and JSON outputs. Useful for logging, debugging, or feeding into downstream
systems.

### `save_outputs_as_markdown(path)` — human-readable report

```python
compiler.save_outputs_as_markdown("outputs/run_report.md")
```

The Markdown report includes, for each node where `show: true`:
- Node ID
- Response text or JSON output
- Input and output token counts
- Elapsed time
- Context utilization (when `context_window` is declared on the model)

Example output for a node:

```markdown
## classifier

**Response:**
billing

**Tokens:** input=245  output=8
**Time:** 0.42s
**Context utilization:** 245 / 32 768 (0.7%)
```

---

## 3. Intermediate: `show` flag

The `show` flag on a node controls whether it appears in the Markdown report.
A node with `show: false` still executes and is included in `get_outputs()` —
only the markdown output is affected.

```yaml
nodes:
  - id: "pre_filter"
    show: false      # internal step — omit from report

  - id: "main_response"
    show: true       # customer-visible — include in report
```

This is useful for guard nodes, pre-processors, and other internal steps that
are not meant to be surfaced in the final report.

---

## 4. Advanced: context window per model in a multi-provider graph

Each model in the `models:` list can have its own `context_window`. Nodes
inherit the value from their assigned model.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    context_window: 32768       # 32 K

  - llm: "anthropic"
    model: "claude-sonnet-4-6"
    api_key: "sk-ant-..."
    context_window: 200000      # 200 K

nodes:
  - id: "fast_node"
    model: 0   # context_window = 32768

  - id: "deep_node"
    model: 1   # context_window = 200000
```

```python
for node in compiler.get_outputs().nodes:
    if node.context_window:
        print(f"[{node.node_id}] window={node.context_window}")
```

---

## 5. Advanced: ReAct compaction with `context_window`

When a ReAct controller has `resume: true`, compaction triggers when:

```
input_size ≥ context_window × resume_threshold
```

Without `context_window`, `max_tokens` is used as the denominator — a much
smaller and less accurate proxy. The difference matters:

| Scenario | Denominator | Threshold at 0.80 |
|---|---|---|
| `context_window: 32768` | 32 768 tokens | 26 214 tokens |
| No `context_window`, `max_tokens: 512` | 512 tokens | 410 tokens → compacts on turn 1 |

Always set `context_window` when using long ReAct loops with `resume: true`.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"
    context_window: 32768

nodes:
  - id: "controller"
    model: 0
    max_tokens: 512
    react:
      max_iterations: 20
      resume: true
      resume_threshold: 0.80    # compact when 80% of 32768 tokens are used as input
```

---

## 6. Advanced: custom compaction prompt

The built-in compaction prompt instructs the model to compress the conversation
into a dense state record. To use your own:

```yaml
react_compact_prompts:
  - template:
      system_template:
        instruction: |
          You are a conversation compressor. Your task is to reduce
          the conversation history while preserving all key findings,
          decisions, and open questions. Format the output as a
          structured list.
      prompt_template:
        action: |
          Compress the conversation above now.
```

Or load from a file:

```yaml
react_compact_prompts:
  - uri: "./prompts/compact.yml"
```

Index 0 in `react_compact_prompts` overrides the built-in default. The prompt
is used for all controllers in the graph.

---

## 7. Monitoring token usage across `compile()` calls

Call `compile()` multiple times on the same instance (e.g. in a chat loop)
and track cumulative token usage:

```python
from kegal import Compiler

total_input = 0
total_output = 0

with Compiler(uri="chat.yml") as compiler:
    for turn, message in enumerate(user_messages, start=1):
        compiler.user_message = message
        compiler.compile()

        outputs = compiler.get_outputs()
        total_input  += outputs.input_size
        total_output += outputs.output_size

        print(f"Turn {turn}: +{outputs.input_size} in / +{outputs.output_size} out")
        print(f"  Running total: {total_input} in / {total_output} out")
```

> `compile()` resets the outputs at the start of each call — `get_outputs()`
> always returns data from the **most recent** run.

---

## Key points

- `context_window` is optional but strongly recommended when using ReAct
  with `resume: true` or when you want utilization percentages in the report.
- `show: false` hides a node from the markdown report but does not skip its
  execution.
- `get_outputs()` always returns the most recent `compile()` result.
- `save_outputs_as_json()` and `save_outputs_as_markdown()` can be called
  multiple times; each call overwrites the previous file at that path.
- The `context_window` value on `CompiledNodeOutput` is `None` if the model
  did not declare it.

---

> **Related tutorials:**
> [12 ReAct loop](12_react_loop.md) — resume and compaction in practice  
> [10 Multi-provider graphs](10_multi_provider.md) — `context_window` per provider
