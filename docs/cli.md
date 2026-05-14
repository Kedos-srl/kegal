# CLI Reference

After installing KeGAL, the `kegal` command is available in your shell.

```
kegal [--version] run [path]
```

## Version

```bash
kegal --version
# kegal 0.1.2.8
```

## Project layout

A KeGAL project is a directory containing a mandatory `kegal.yml` configuration file and one or more graph definition files:

```
my_project/
├── kegal.yml       ← required
└── my_graph.yml    ← referenced by kegal.yml
```

If `kegal.yml` is absent, the CLI prints an error to stderr and exits with code 1.

## kegal.yml fields

| Field | Required | Values | Description |
|-------|----------|--------|-------------|
| `graph` | **yes** | file path | Path to the graph YAML/JSON, relative to `kegal.yml` |
| `mode` | no | `once` (default), `chat` | Execution mode |
| `message` | no | `true` / `false` | Prompt for `user_message` each turn — **chat mode only** |
| `chunks` | no | `true` / `false` | Prompt for RAG chunks each turn — **chat mode only** |

Unknown keys in `kegal.yml` are reported as a warning to stderr and ignored.

Setting `message` or `chunks` with `mode: once` prints a warning — those flags are silently ignored in once mode.

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

> **Warning — chat mode with `message: false`**: the graph runs on every iteration with no user input. The CLI prints a warning to stderr. This is only useful if the graph derives all its input from blackboard state or external sources.

## Running a project

```bash
# run from inside the project folder
kegal run

# or pass the project path explicitly
kegal run path/to/my_project
```

Both forms look for `kegal.yml` inside the given folder.

## Output

The CLI prints the output of every node that has `show: true` in the graph YAML. When more than one visible node exists, each output is prefixed with its node ID and separated by a blank line:

```
[node_a]
First node output.

[node_b]
{"result": "structured output"}
```

For single-output graphs the prefix is omitted.

If no nodes have `show: true`, the CLI prints a hint to stderr:

```
(no output — set show: true on nodes you want to display)
```

## Error handling

Configuration errors (invalid graph YAML, unknown model, MCP connection failure) and runtime errors (DAG cycle, tool dispatch failure, parallel node failure) are caught and printed as a clean message:

```
Error: Edge references unknown node 'missing_node'
```

The process exits with code 1. In `chat` mode, per-turn compile errors print the message and continue the loop so the session is not lost; only Compiler initialisation errors exit.

## Verbose output

Enable `verbose: true` in the graph YAML to see a colored progress trace on stderr while the graph runs. See [graph_doc.md §9](graph_doc.md#9-graph) for the full description of verbose output.
