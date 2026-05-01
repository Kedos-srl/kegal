"""
Standalone runner for the research ReAct graph.

Run from the project root with:
    conda run -n red python test/run_react_research.py

Logs stream in real time — no pytest buffering.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(line_buffering=True)

# ANSI colours
_C = {
    "header":  "\033[1;36m",   # bold cyan   — loop start/end
    "iter":    "\033[1;34m",   # bold blue   — iteration header
    "key":     "\033[90m",     # dark grey   — field labels
    "agent":   "\033[1;33m",   # bold yellow — agent name
    "warn":    "\033[1;31m",   # bold red    — warnings
    "reset":   "\033[0m",
}


class _ReactDisplay(logging.Handler):
    """Intercepts [ReAct] log records and prints them without any log prefix."""

    def emit(self, record):
        msg = record.getMessage()
        if "[ReAct]" not in msg:
            return

        line = msg.split("[ReAct] ", 1)[-1]
        is_warn = record.levelno >= logging.WARNING

        # colour specific fragments
        if is_warn:
            line = f"{_C['warn']}{line}{_C['reset']}"
        elif line.startswith("──"):
            line = f"{_C['header']}{line}{_C['reset']}"
        elif line.startswith("┌─"):
            line = f"{_C['iter']}{line}{_C['reset']}"
        elif "→ dispatching" in line:
            agent = line.split("'")[1] if "'" in line else ""
            line = line.replace(f"'{agent}'", f"{_C['agent']}'{agent}'{_C['reset']}")
        elif line.startswith("│  ") and ":" in line:
            label, _, rest = line.partition(":")
            line = f"{_C['key']}{label}:{_C['reset']}{rest}"

        print(line, flush=True)


logging.root.setLevel(logging.INFO)
logging.root.handlers = [_ReactDisplay()]
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from kegal import Compiler  # noqa: E402 — import after logging config

GRAPH = Path(__file__).parent / "graphs" / "react_research_graph.yml"

with Compiler(uri=str(GRAPH)) as compiler:
    compiler.compile()
    trace = compiler.get_react_trace("research_controller")

print()
print("=" * 60)
print(f"  done       : {trace.done}")
print(f"  iterations : {trace.total_iterations}")
print(f"  tokens in  : {trace.total_controller_input_tokens}")
print(f"  tokens out : {trace.total_controller_output_tokens}")
if trace.final_answer:
    print()
    print("  FINAL ANSWER:")
    print(f"  {trace.final_answer}")
print("=" * 60)
