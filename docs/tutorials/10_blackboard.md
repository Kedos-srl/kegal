# Tutorial 10: Blackboard — Shared Markdown Pipeline

The **blackboard** is a persistent markdown buffer that nodes can read from
and write to during a single `compile()` run. It implements the classic
[Blackboard architectural pattern](https://en.wikipedia.org/wiki/Blackboard_(design_pattern)):
a shared workspace where multiple agents contribute and consume content.

KeGAL supports **multiple named boards** in the same graph, each with its own
file, cleanup behaviour, and optional import chain.

---

## 1. Basic: single board, three-node pipeline

Every board interaction is declared with three fields on the node:
- `id` — which board to access (must match a `BlackboardEntry.id`)
- `read` — whether to inject the board's current content as `{blackboard}`
- `write` — whether to append the node's response to the board after execution

This produces three natural node categories:

| Category | `read` | `write` | Role |
|----------|--------|---------|------|
| Cat-1 | `false` | `true`  | **Writer** — seeds the board |
| Cat-2 | `true`  | `true`  | **Enricher** — reads then extends |
| Cat-3 | `true`  | `false` | **Reader** — consumes the final board |

The compiler infers the execution order automatically: Cat-1 → Cat-2 (in
parallel) → Cat-3.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"

blackboard:
  path: ./                    # directory for board files (relative to YAML)
  boards:
    - id: main
      file: BLACKBOARD.md
      cleanup: true           # truncate at Compiler init (default)

prompts:
  - template:  # 0 — writer: seeds the board
      system_template:
        role: |
          You are a research assistant.
          Write a concise overview of the topic, max 200 words.
      prompt_template:
        topic: "{user_message}"

  - template:  # 1 — enricher_a: economic analysis
      system_template:
        role: |
          You are an economic analyst.
          Read the overview below and add 3 bullet points about economic implications.
      prompt_template:
        overview: |
          {blackboard}

  - template:  # 2 — enricher_b: risk analysis
      system_template:
        role: |
          You are a risk analyst.
          Read the overview below and add 3 bullet points about key risks.
      prompt_template:
        overview: |
          {blackboard}

  - template:  # 3 — reader: synthesises the full board
      system_template:
        role: |
          You are a report writer.
          Synthesise everything below into an executive summary of max 150 words.
      prompt_template:
        board: |
          {blackboard}

nodes:
  - id: "writer"           # Cat-1
    model: 0
    temperature: 0.3
    max_tokens: 300
    show: false
    blackboard:
      id: main
      read: false
      write: true
    prompt: { template: 0, user_message: true }

  - id: "enricher_a"       # Cat-2
    model: 0
    temperature: 0.5
    max_tokens: 256
    show: false
    blackboard:
      id: main
      read: true
      write: true
    prompt: { template: 1 }

  - id: "enricher_b"       # Cat-2 — runs in parallel with enricher_a
    model: 0
    temperature: 0.5
    max_tokens: 256
    show: false
    blackboard:
      id: main
      read: true
      write: true
    prompt: { template: 2 }

  - id: "summarizer"       # Cat-3
    model: 0
    temperature: 0.4
    max_tokens: 300
    show: true
    blackboard:
      id: main
      read: true
      write: false
    prompt: { template: 3 }

edges:
  - node: "writer"
  - node: "enricher_a"
  - node: "enricher_b"
  - node: "summarizer"
```

```python
from kegal import Compiler

with Compiler(uri="blackboard_graph.yml") as compiler:
    compiler.user_message = "Impact of autonomous vehicles on urban planning."
    compiler.compile()

    for node in compiler.get_outputs().nodes:
        if node.show:
            for msg in node.response.messages or []:
                print(msg)
```

After `compile()` the file `BLACKBOARD.md` on disk contains the full
accumulated thread: the writer's overview plus both enrichers' additions.

---

## 2. Intermediate: `cleanup: false` — accumulate across runs

By default `cleanup: true` truncates the board file at `Compiler`
construction. Set `cleanup: false` to keep existing content and append new
writes on top of it. This is useful for logs, journals, or multi-session
accumulation.

```yaml
blackboard:
  path: ./logs/
  boards:
    - id: journal
      file: journal.md
      cleanup: false       # keep all previous content
```

Each `compile()` call — across separate `Compiler` instances — appends to
the same file. No content is ever lost between runs.

---

## 3. Intermediate: multiple boards

Declare multiple boards in the same graph. Nodes reference them by ID.
Each board has its own file; different nodes can write to different boards.

```yaml
blackboard:
  path: ./
  boards:
    - id: facts
      file: facts.md
      cleanup: true
    - id: report
      file: report.md
      cleanup: true

nodes:
  - id: "researcher"
    blackboard:
      id: facts       # writes to facts.md
      read: false
      write: true
    ...

  - id: "writer"
    blackboard:
      id: report      # writes to report.md
      read: true      # reads report.md (+ any imports)
      write: true
    ...

  - id: "editor"
    blackboard:
      id: report
      read: true
      write: false
    ...
```

---

## 4. Advanced: board import chains

The `import` key on a `BlackboardEntry` prepends other boards' content at
**read time**. Files on disk stay separate; only the `{blackboard}`
placeholder delivered to the node includes the imported content.

```yaml
blackboard:
  path: ./
  boards:
    - id: facts
      file: facts.md
      cleanup: true

    - id: report
      file: report.md
      cleanup: true
      import: [facts]       # when reading 'report', prepend 'facts' first
```

**Assembly order** when node reads `report`:
```
content of facts.md  +  content of report.md
```

```yaml
nodes:
  - id: "researcher"
    blackboard: { id: facts, read: false, write: true }
    ...

  - id: "writer"
    blackboard:
      id: report
      read: true    # {blackboard} = facts content + report content
      write: true
    prompt:
      template: 1   # template uses {blackboard}
```

---

## 5. Advanced: full two-board pipeline

A researcher accumulates raw notes into `facts`. A writer reads both `facts`
and the current `report` draft (via `import`), then extends the draft. An
editor reads the final draft for review.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"

blackboard:
  path: ./
  boards:
    - id: facts
      file: facts.md
      cleanup: true
    - id: report
      file: report.md
      cleanup: true
      import: [facts]

prompts:
  - template:  # 0 — researcher
      system_template:
        role: Write concise factual notes about the topic. Max 5 bullet points.
      prompt_template:
        topic: "{user_message}"

  - template:  # 1 — writer
      system_template:
        role: |
          You are a science writer. The research notes and existing report draft
          are below. Add one new paragraph to the article.
      prompt_template:
        material: |
          {blackboard}

  - template:  # 2 — editor
      system_template:
        role: |
          You are an editor. Review the article below and summarise any
          improvements needed in one sentence.
      prompt_template:
        article: |
          {blackboard}

nodes:
  - id: "researcher"        # Cat-1 on 'facts'
    model: 0
    temperature: 0.3
    max_tokens: 300
    show: false
    blackboard: { id: facts, read: false, write: true }
    prompt: { template: 0, user_message: true }

  - id: "writer"            # Cat-2 on 'report' (reads facts via import)
    model: 0
    temperature: 0.5
    max_tokens: 500
    show: false
    blackboard: { id: report, read: true, write: true }
    prompt: { template: 1 }

  - id: "editor"            # Cat-3 on 'report'
    model: 0
    temperature: 0.3
    max_tokens: 256
    show: true
    blackboard: { id: report, read: true, write: false }
    prompt: { template: 2 }

edges:
  - node: "researcher"
  - node: "writer"
  - node: "editor"
```

---

## 6. Reading board content in Python

After `compile()`, board files on disk hold the accumulated text. Read them
directly with standard file I/O:

```python
from pathlib import Path
from kegal import Compiler

with Compiler(uri="blackboard_graph.yml") as compiler:
    compiler.user_message = "Autonomous vehicles."
    compiler.compile()

# Board files are available after compile() even while inside the `with` block
board_content = Path("BLACKBOARD.md").read_text(encoding="utf-8")
print(board_content)
```

---

## Key points

- Board IDs must be unique within the graph; duplicate IDs raise `ValueError`
  at parse time.
- Node `blackboard.id` must reference a declared board ID; unknown IDs raise
  `ValueError` at `Compiler` construction.
- Cat-1 → Cat-2 (parallel) → Cat-3 ordering is inferred automatically — no
  `children`/`fan_in` declarations are needed for the basic pattern.
- `cleanup: true` (default) truncates the board at init; `cleanup: false`
  preserves existing content.
- `import` is evaluated at read time — imported boards are prepended to the
  reading node's `{blackboard}` but files on disk are never merged.
- Empty segments (missing or empty files) are skipped during import assembly.

---

> **Related tutorials:**
> [04 Fan-out and fan-in](04_fan_out_fan_in.md) — explicit edge-based parallelism  
> [01 Message passing](01_message_passing.md) — alternative data-flow mechanism
