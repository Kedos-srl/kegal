"""Tests for the Cat-2 blackboard write-ordering fix.

Cat-2 nodes (blackboard.read=True, blackboard.write=True) run in parallel.
Their writes must be applied to the board in YAML declaration order, not in
thread-completion order.

The fix: before the parallel phase, the compiler pre-initialises a dict keyed
by node_id in declaration order. Each thread writes to its own key. After all
threads join, the dict is flushed to the board by iterating its keys — which
Python guarantees are in insertion (declaration) order.
"""

import threading
import unittest
from unittest.mock import MagicMock

from kegal.compiler import Compiler, CompiledOutput
from kegal.graph import Graph
from kegal.graph_blackboard import BlackboardEntry
from kegal.llm.llm_model import LLmResponse


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_compiler_with_two_cat2_nodes() -> Compiler:
    """Build a minimal Compiler with one board and two Cat-2 nodes declared
    in order: cat2_a first, cat2_b second."""
    source = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "blackboard": {
            "path": "/tmp",
            "boards": [{"id": "main", "file": "main.md", "cleanup": True}],
        },
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": [
            {
                "id": "cat2_a",
                "model": 0, "temperature": 0.0, "max_tokens": 10, "show": False,
                "prompt": {"template": 0},
                "blackboard": {"id": "main", "read": True, "write": True},
            },
            {
                "id": "cat2_b",
                "model": 0, "temperature": 0.0, "max_tokens": 10, "show": False,
                "prompt": {"template": 0},
                "blackboard": {"id": "main", "read": True, "write": True},
            },
        ],
        "edges": [{"node": "cat2_a"}, {"node": "cat2_b"}],
    }
    graph = Graph.model_validate(source)

    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    c.clients = [MagicMock()]
    c.prompts = [{"system": "", "user": ""}]
    c.images = None
    c.documents = None
    c.tools = None
    c.chat_history = None
    c.user_message = None
    c.retrieved_chunks = None
    c._board_entries = {"main": BlackboardEntry(id="main", file="main.md")}
    c._boards = {"main": ""}
    c._board_paths = {"main": None}      # no actual file on disk
    c._blackboard_lock = threading.Lock()
    c._blackboard_write_buffer = None   # new attribute — None outside Cat-2 phase
    c._message_passing_lock = threading.Lock()
    c._outputs_lock = threading.Lock()
    c.outputs = CompiledOutput()
    c.message_passing = []
    c.mcp_handlers = {}
    c.tool_executors = {}
    c.graph_mcp_servers = []
    c._react_trace = {}
    c._history_auto_paths = {}
    c._react_controllers = c._build_react_controller_map()
    return c


# ===========================================================================
# Buffer flush — ordering guarantee
# ===========================================================================

class TestBlackboardWriteOrderFlush(unittest.TestCase):

    def test_flush_applies_writes_in_declaration_order(self):
        """When cat2_b completes before cat2_a the board must still contain
        cat2_a's content before cat2_b's after the buffer is flushed."""
        c = _make_compiler_with_two_cat2_nodes()

        # Pre-initialise in declaration order (a first, b second)
        c._blackboard_write_buffer = {"main": {"cat2_a": "", "cat2_b": ""}}

        # Simulate cat2_b finishing first (reverse of declaration order)
        c._blackboard_write_buffer["main"]["cat2_b"] = "section B"
        c._blackboard_write_buffer["main"]["cat2_a"] = "section A"

        c._flush_blackboard_write_buffer()

        board = c._boards["main"]
        self.assertIn("section A", board)
        self.assertIn("section B", board)
        self.assertLess(
            board.index("section A"), board.index("section B"),
            "section A (declared first) must appear before section B regardless "
            "of thread-completion order",
        )

    def test_flush_clears_buffer(self):
        """_flush_blackboard_write_buffer must set _blackboard_write_buffer to None."""
        c = _make_compiler_with_two_cat2_nodes()
        c._blackboard_write_buffer = {"main": {"cat2_a": "x", "cat2_b": "y"}}

        c._flush_blackboard_write_buffer()

        self.assertIsNone(c._blackboard_write_buffer)

    def test_flush_skips_empty_entries(self):
        """Nodes that produced no output (empty string) must not add blank
        sections to the board."""
        c = _make_compiler_with_two_cat2_nodes()
        c._boards["main"] = "seed"
        c._blackboard_write_buffer = {"main": {"cat2_a": "real output", "cat2_b": ""}}

        c._flush_blackboard_write_buffer()

        board = c._boards["main"]
        self.assertIn("real output", board)
        # No extra blank separator should be appended for the empty entry
        self.assertNotIn("\n\n\n\n", board)


# ===========================================================================
# _update_blackboard — buffer vs. direct write
# ===========================================================================

class TestUpdateBlackboardBuffering(unittest.TestCase):

    def _response(self, text: str) -> LLmResponse:
        r = LLmResponse()
        r.messages = [text]
        return r

    def test_writes_to_buffer_when_buffer_entry_exists(self):
        """During the Cat-2 phase _update_blackboard must store output in the
        buffer, NOT write directly to _boards."""
        c = _make_compiler_with_two_cat2_nodes()
        c._blackboard_write_buffer = {"main": {"cat2_a": "", "cat2_b": ""}}

        c._update_blackboard(c.nodes["cat2_a"], self._response("cat2_a output"))

        self.assertEqual(c._boards["main"], "",
                         "_boards must not be modified during the buffered phase")
        self.assertEqual(c._blackboard_write_buffer["main"]["cat2_a"], "cat2_a output")

    def test_writes_directly_when_no_buffer(self):
        """Outside the Cat-2 phase (buffer is None) _update_blackboard must
        write directly to _boards — Cat-1 behaviour."""
        c = _make_compiler_with_two_cat2_nodes()
        c._blackboard_write_buffer = None

        c._update_blackboard(c.nodes["cat2_a"], self._response("direct output"))

        self.assertIn("direct output", c._boards["main"])

    def test_writes_directly_when_node_not_in_buffer(self):
        """A node whose id is not in the buffer dict must still write directly.
        This covers Cat-1 nodes that run before the buffer is set up."""
        c = _make_compiler_with_two_cat2_nodes()
        # Buffer exists but does NOT contain cat2_a's id
        c._blackboard_write_buffer = {"main": {"cat2_b": ""}}

        c._update_blackboard(c.nodes["cat2_a"], self._response("cat1 style output"))

        self.assertIn("cat1 style output", c._boards["main"])

    def test_no_write_when_response_has_no_messages(self):
        """An empty response must not touch the board or the buffer."""
        c = _make_compiler_with_two_cat2_nodes()
        c._blackboard_write_buffer = {"main": {"cat2_a": "", "cat2_b": ""}}

        empty = LLmResponse()  # messages is None / empty
        c._update_blackboard(c.nodes["cat2_a"], empty)

        self.assertEqual(c._boards["main"], "")
        self.assertEqual(c._blackboard_write_buffer["main"]["cat2_a"], "")


if __name__ == "__main__":
    unittest.main()
