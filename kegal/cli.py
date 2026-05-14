import json
import sys
from pathlib import Path

import yaml

from .compiler import Compiler
from . import __version__

_KNOWN_CONFIG_KEYS = {"graph", "mode", "message", "chunks"}


def _load_config(project_path: str) -> tuple[dict, Path]:
    path = Path(project_path).resolve()
    config_file = path / "kegal.yml"
    if not config_file.exists():
        print(f"Error: kegal.yml not found in '{path}'", file=sys.stderr)
        sys.exit(1)
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    unknown = set(config.keys()) - _KNOWN_CONFIG_KEYS
    if unknown:
        print(
            f"Warning: unknown key(s) in kegal.yml ignored: {sorted(unknown)}",
            file=sys.stderr,
        )
    return config, path


def _print_outputs(compiler: Compiler) -> None:
    visible = [n for n in compiler.get_outputs().nodes if n.show]
    if not visible:
        print("(no output — set show: true on nodes you want to display)", file=sys.stderr)
        return
    for i, node in enumerate(visible):
        if i > 0:
            print()
        if len(visible) > 1:
            print(f"[{node.node_id}]")
        if node.response.messages:
            print("\n".join(node.response.messages))
        elif node.response.json_output is not None:
            print(json.dumps(node.response.json_output, indent=2, ensure_ascii=False))


def _run_once(graph_path: Path) -> None:
    try:
        with Compiler(uri=str(graph_path)) as compiler:
            compiler.compile()
            _print_outputs(compiler)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_chat(graph_path: Path, message_enabled: bool, chunks_enabled: bool) -> None:
    if not message_enabled:
        print(
            "Warning: message is false in chat mode — the graph will run "
            "with no user input on each turn.",
            file=sys.stderr,
        )

    try:
        with Compiler(uri=str(graph_path)) as compiler:
            while True:
                try:
                    if message_enabled:
                        msg = input("\nmessage (Ctrl+D to exit): ")
                        compiler.user_message = msg

                    if chunks_enabled:
                        chunks = input("chunks: ")
                        compiler.retrieved_chunks = chunks

                    print()
                    compiler.compile()
                    _print_outputs(compiler)

                except EOFError:
                    print("\nBye.")
                    break
                except KeyboardInterrupt:
                    print()
                    break
                except (ValueError, RuntimeError) as e:
                    print(f"Error: {e}", file=sys.stderr)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_run(args) -> None:
    config, project_dir = _load_config(args.path)

    graph_rel = config.get("graph")
    if not graph_rel:
        print("Error: 'graph' key missing in kegal.yml", file=sys.stderr)
        sys.exit(1)

    graph_path = project_dir / graph_rel
    if not graph_path.exists():
        print(f"Error: graph file '{graph_path}' not found", file=sys.stderr)
        sys.exit(1)

    mode = config.get("mode", "once")
    message_enabled = bool(config.get("message", False))
    chunks_enabled = bool(config.get("chunks", False))

    if mode == "once" and (message_enabled or chunks_enabled):
        flags = [k for k, v in [("message", message_enabled), ("chunks", chunks_enabled)] if v]
        print(
            f"Warning: {flags} set in kegal.yml but ignored in 'once' mode "
            f"(only applies to 'chat' mode).",
            file=sys.stderr,
        )

    if mode == "chat":
        _run_chat(graph_path, message_enabled, chunks_enabled)
    elif mode == "once":
        _run_once(graph_path)
    else:
        print(
            f"Error: unknown mode '{mode}' in kegal.yml (expected: chat, once)",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="kegal",
        description="KeGAL — Kedos Graph Agent for LLM",
    )
    parser.add_argument(
        "--version", action="version", version=f"kegal {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a KeGAL project")
    run_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the project folder containing kegal.yml (default: current directory)",
    )
    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
