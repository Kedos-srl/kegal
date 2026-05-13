# CLI Reference

After installing KeGAL, the `kegal` command is available in your shell.

```
kegal run [path]
```

## Project layout

A KeGAL project is a directory containing a mandatory `kegal.yml` configuration file and one or more graph definition files:

```
my_project/
├── kegal.yml       ← required
└── my_graph.yml    ← referenced by kegal.yml
```

If `kegal.yml` is absent, the CLI logs an error and exits.

## kegal.yml fields

| Field | Required | Values | Description |
|-------|----------|--------|-------------|
| `graph` | **yes** | file path | Path to the graph YAML/JSON, relative to `kegal.yml` |
| `mode` | no | `once` (default), `chat` | Execution mode |
| `message` | no | `true` / `false` | Whether to prompt the user for a message on each turn (chat mode) |
| `chunks` | no | `true` / `false` | Whether to prompt the user for RAG chunks on each turn (chat mode) |

## Modes

### `once` — single run

The graph is compiled once, outputs are printed, and the process exits. All inputs are taken from the graph YAML.

```yaml
# kegal.yml
graph: my_graph.yml
mode: once
```

```bash
kegal run
```

### `chat` — interactive loop

The CLI keeps a loop alive and prompts for user input before each `compile()` call. Exit with **Ctrl+D**.

```yaml
# kegal.yml
graph: my_graph.yml
mode: chat
message: true   # prompt for user_message each turn
chunks: false   # do not prompt for RAG chunks
```

```bash
kegal run

message (Ctrl+D to exit): What is the capital of France?

[answer_node]
Paris is the capital of France.

message (Ctrl+D to exit): ^D
Bye.
```

If `message: true` and `chunks: true`, the CLI shows both prompts on each turn:

```
message (Ctrl+D to exit): Summarise this text for me.
chunks: <paste your document chunks here>
```

!!! warning "chat mode with `message: false`"
    If `mode: chat` and `message: false`, the graph runs on every iteration with no user input. The CLI prints a warning to stderr. This is only useful if the graph derives all its input from blackboard state or external sources.

## Running a project

```bash
# run from inside the project folder
kegal run

# or pass the project path explicitly
kegal run path/to/my_project
```

Both forms look for `kegal.yml` inside the given folder.

## Output

The CLI prints the output of every node that has `show: true` in the graph YAML. When more than one visible node exists, each output is prefixed with its node ID:

```
[node_a]
First node output.

[node_b]
{"result": "structured output"}
```

For single-output graphs the prefix is omitted.
