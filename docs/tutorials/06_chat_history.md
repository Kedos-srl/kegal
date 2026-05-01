# Tutorial 6: Chat History

Chat history lets a node begin its LLM call with prior conversation turns,
making the model aware of context from earlier in the session. Each history
**scope** is a named list of `{role, content}` message pairs; a node
references its scope by name via `NodePrompt.chat_history`.

---

## 1. Basic: inline history in YAML

Declare history directly in the graph file. Useful for fixed few-shot
examples that never change.

```yaml
models:
  - llm: "ollama"
    model: "qwen2.5:7b"
    host: "http://localhost:11434"

chat_history:
  few_shot:
    - role: "user"
      content: "What is the capital of France?"
    - role: "assistant"
      content: "Paris."
    - role: "user"
      content: "And of Germany?"
    - role: "assistant"
      content: "Berlin."

prompts:
  - template:
      system_template:
        role: You are a geography assistant.
      prompt_template:
        question: "{user_message}"

nodes:
  - id: "assistant"
    model: 0
    temperature: 0.3
    max_tokens: 128
    show: true
    prompt:
      template: 0
      user_message: true
      chat_history: "few_shot"   # injects the two Q&A pairs before the new question

edges:
  - node: "assistant"
```

The model sees the history as genuine prior conversation turns, not as part
of the system prompt. The current `user_message` follows them.

```python
from kegal import Compiler

with Compiler(uri="few_shot.yml") as compiler:
    compiler.user_message = "What is the capital of Italy?"
    compiler.compile()

    for msg in compiler.get_outputs().nodes[0].response.messages:
        print(msg)   # "Rome."
```

---

## 2. Intermediate: injecting history at runtime

When history is session-specific, manage it in Python and assign it before
each `compile()` call.

```python
from kegal import Compiler

# Build or load history from your session store
history = [
    {"role": "user",      "content": "Summarise the project status."},
    {"role": "assistant", "content": "The project is on track. Two milestones remain."},
    {"role": "user",      "content": "When is the next milestone due?"},
    {"role": "assistant", "content": "The design review is due on Friday."},
]

with Compiler(uri="assistant.yml") as compiler:
    compiler.chat_history = {"session": history}
    compiler.user_message = "Which milestone comes after the design review?"
    compiler.compile()
```

> `compiler.chat_history` is a plain dict — assigning to it overwrites any
> history loaded from the YAML. To extend rather than replace, read the
> existing dict first:
>
> ```python
> compiler.chat_history["session"].append({"role": "user", "content": "..."})
> ```

---

## 3. Intermediate: loading history from a file or URL

`add_chat_history` is a convenience helper that accepts a local JSON file, a
remote `https://` URL, or an inline list — exactly one source per call.

```python
from pathlib import Path
from kegal import Compiler

with Compiler(uri="assistant.yml") as compiler:
    # from a local JSON file
    compiler.add_chat_history("session", file=Path("sessions/user_42.json"))
    compiler.user_message = "Continue from where we left off."
    compiler.compile()
```

```python
with Compiler(uri="assistant.yml") as compiler:
    # from a remote endpoint (https only)
    compiler.add_chat_history(
        "session",
        uri="https://sessions.example.com/api/history/user_42"
    )
    compiler.user_message = "What did we discuss last time?"
    compiler.compile()
```

```python
with Compiler(uri="assistant.yml") as compiler:
    # from an inline list
    compiler.add_chat_history("session", history=[
        {"role": "user",      "content": "Hello."},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ])
    compiler.user_message = "Tell me more."
    compiler.compile()
```

The inline list is **copied** — subsequent modifications to the original list
do not affect the history stored in the compiler.

---

## 4. Intermediate: file-based scope in YAML

Instead of an inline array, a scope can point to an external JSON file
managed on disk. The compiler loads it at construction time.

```yaml
chat_history:
  session_a:
    path: ./history/session_a.json   # local path relative to the YAML file
    auto: false                       # caller manages persistence (default)

  shared_examples:
    path: https://example.com/examples.json   # https URL — fetched at init
```

For local paths: if the file does not exist the scope starts empty. For
remote URLs: only `https://` is accepted (`http://` raises `ValueError`).

```python
# Load the graph — session_a.json is read at this point
with Compiler(uri="assistant.yml") as compiler:
    compiler.user_message = "Continue our discussion."
    compiler.compile()
    # You must save the updated history manually when auto=false
    import json
    from pathlib import Path
    Path("history/session_a.json").write_text(
        json.dumps(compiler.chat_history["session_a"], indent=2)
    )
```

---

## 5. Advanced: auto-append mode

Set `auto: true` on a file-based scope to have KeGAL automatically write
the user and assistant turns to the file at the end of every `compile()`.
This turns the graph into a stateful chat session with zero bookkeeping.

```yaml
chat_history:
  session:
    path: ./history/session.json
    auto: true    # KeGAL writes user+assistant turns after every compile()
```

```yaml
nodes:
  - id: "assistant"
    model: 0
    temperature: 0.3
    max_tokens: 256
    show: true
    prompt:
      template: 0
      user_message: true
      chat_history: "session"
```

```python
from kegal import Compiler

# Turn 1
with Compiler(uri="chat.yml") as compiler:
    compiler.user_message = "What is the capital of France?"
    compiler.compile()
    # session.json now contains:
    # [{"role": "user",      "content": "What is the capital of France?"},
    #  {"role": "assistant", "content": "Paris."}]

# Turn 2 — new Compiler instance reloads the file
with Compiler(uri="chat.yml") as compiler:
    compiler.user_message = "And its population?"
    compiler.compile()
    # session.json now has all four turns
```

Each new `Compiler` instance reloads the file, so the accumulating history
is always available to the model.

**Constraints for `auto: true`:**
- Only valid for local file paths — remote URLs cannot be written back.
- The scope must be assigned to at most one node (see §6 below).

---

## 6. Advanced: multiple scopes

Different nodes in the same graph can reference different history scopes.
Each scope is fully independent.

```yaml
chat_history:
  finance_ctx:
    - role: "user"
      content: "Our Q3 revenue was €4.2 M."
    - role: "assistant"
      content: "Noted."
  legal_ctx:
    path: ./history/legal.json
    auto: true

nodes:
  - id: "finance_analyst"
    prompt:
      template: 0
      chat_history: "finance_ctx"

  - id: "legal_analyst"
    prompt:
      template: 1
      chat_history: "legal_ctx"
```

**Scope uniqueness:** each scope key may be referenced by at most one node.
Assigning the same scope to two different nodes raises `ValueError` at
`Compiler` construction time — this prevents ambiguous auto-append writes.

---

## 7. Advanced: chat history in a ReAct controller

`chat_history` on a ReAct controller seeds its conversation buffer. The
controller's iterative LLM calls build on top of this foundation.

```yaml
chat_history:
  research_ctx:
    path: ./history/research_ctx.json
    auto: true

nodes:
  - id: "research_controller"
    ...
    react:
      max_iterations: 8
    prompt:
      template: 0
      user_message: true
      chat_history: "research_ctx"   # seeds the ReAct conversation buffer
```

The auto-append writes the final user message and `final_answer` to the file,
so the next run knows what was decided in previous sessions.

---

## Key points

- `chat_history` is a dict of named scopes; each scope is a list of
  `{role, content}` pairs.
- Inline scopes (array in YAML) are always managed by the caller.
- File-based scopes are loaded at `Compiler` construction time; `auto: true`
  writes back after each `compile()`.
- `auto: true` is not supported for remote URL scopes.
- Each scope may be assigned to at most one node — sharing a scope between
  two nodes raises `ValueError`.
- `add_chat_history(id, *, file, uri, history)` accepts exactly one source.

---

> **Related tutorials:**
> [12 ReAct loop](12_react_loop.md) — using chat_history to seed a controller's conversation  
> [05 RAG](05_rag.md) — combining retrieved context with conversation history
