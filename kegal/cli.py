import json
import sys
from pathlib import Path

import yaml

from .compiler import Compiler


def _load_config(project_path: str) -> tuple[dict, Path]:
    path = Path(project_path).resolve()
    config_file = path / "kegal.yml"
    if not config_file.exists():
        print(f"Error: kegal.yml not found in '{path}'", file=sys.stderr)
        sys.exit(1)
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config, path


def _print_outputs(compiler: Compiler) -> None:
    visible = [n for n in compiler.get_outputs().nodes if n.show]
    for node in visible:
        if len(visible) > 1:
            print(f"[{node.node_id}]")
        if node.response.messages:
            print("\n".join(node.response.messages))
        elif node.response.json_output is not None:
            print(json.dumps(node.response.json_output, indent=2, ensure_ascii=False))


def _run_once(graph_path: Path) -> None:
    with Compiler(uri=str(graph_path)) as compiler:
        compiler.compile()
        _print_outputs(compiler)


def _run_chat(graph_path: Path, message_enabled: bool, chunks_enabled: bool) -> None:
    if not message_enabled:
        print(
            "Warning: message is false in chat mode — the graph will run "
            "with no user input on each turn.",
            file=sys.stderr,
        )

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
