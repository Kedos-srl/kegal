"""
Unit tests for three features that lacked coverage:
  - GraphNode.max_tool_calls      (TestMaxToolCalls)
  - Graph.verbose logging setup   (TestVerboseFlag)
  - NodeMcpServerRef tool filter  (TestNodeMcpServerRefTools)

All tests are self-contained — no real LLM, no network, no Ollama.
"""

import logging
import threading
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from kegal.compiler import Compiler, CompiledOutput
from kegal.graph import Graph
from kegal.graph_node import NodeMcpServerRef
from kegal.llm.llm_model import LLmResponse, LLMFunctionCall, LLMTool


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _graph_source(**overrides) -> dict:
    base = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": [],
        "edges": [],
    }
    base.update(overrides)
    return base


def _node_cfg(nid: str = "n", max_tool_calls: int | None = None) -> dict:
    cfg: dict = {
        "id": nid, "model": 0, "temperature": 0.0, "max_tokens": 100,
        "show": False, "prompt": {"template": 0},
    }
    if max_tool_calls is not None:
        cfg["max_tool_calls"] = max_tool_calls
    return cfg


def _bare_compiler(nodes_cfg=None, edges_cfg=None) -> tuple[Compiler, MagicMock]:
    """Build a Compiler via object.__new__ with a mocked LLM client (no LLM needed)."""
    nodes_cfg = nodes_cfg or [_node_cfg()]
    edges_cfg = edges_cfg or []
    graph = Graph.model_validate(_graph_source(nodes=nodes_cfg, edges=edges_cfg))
    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    mock_client = MagicMock()
    c.clients = [mock_client]
    c.context_windows = [None]
    c.prompts = [{"system": "", "user": ""}]
    c.images = None
    c.documents = None
    c.tools = None
    c.chat_history = {}
    c._history_auto_paths = {}
    c.user_message = "hello"
    c.retrieved_chunks = None
    c._board_entries = {}
    c._boards = {}
    c._board_paths = {}
    c._blackboard_lock = threading.Lock()
    c._message_passing_lock = threading.Lock()
    c._outputs_lock = threading.Lock()
    c.outputs = CompiledOutput()
    c.message_passing = []
    c.mcp_handlers = {}
    c.tool_executors = {}
    c.graph_mcp_servers = []
    c._react_trace = {}
    c.react_compact_prompts = []
    c._react_controllers = c._build_react_controller_map()
    return c, mock_client


def _tool_resp(input_size: int = 50) -> LLmResponse:
    return LLmResponse(
        tools=[LLMFunctionCall(name="dummy_tool", parameters={})],
        input_size=input_size,
    )


def _text_resp() -> LLmResponse:
    return LLmResponse(messages=["final answer"], input_size=50)


# ===========================================================================
# TestMaxToolCalls
# ===========================================================================

class TestMaxToolCalls(unittest.TestCase):

    def test_respects_custom_limit(self):
        """Loop exits after max_tool_calls iterations then makes one synthesis call."""
        c, mock_client = _bare_compiler([_node_cfg("A", max_tool_calls=3)])
        # 3 tool responses + 1 synthesis response
        mock_client.complete.side_effect = [
            _tool_resp(), _tool_resp(), _tool_resp(), _text_resp(),
        ]
        with patch.object(c, "_execute_tool_call", return_value="ok"):
            c._run_tool_loop(c.nodes["A"], {"temperature": 0.0, "max_tokens": 100})
        self.assertEqual(mock_client.complete.call_count, 4)

    def test_default_is_ten_iterations(self):
        """When max_tool_calls is None the loop cap defaults to 10."""
        c, mock_client = _bare_compiler([_node_cfg("A", max_tool_calls=None)])
        # 10 tool responses + 1 synthesis
        mock_client.complete.side_effect = [_tool_resp()] * 10 + [_text_resp()]
        with patch.object(c, "_execute_tool_call", return_value="ok"):
            c._run_tool_loop(c.nodes["A"], {"temperature": 0.0, "max_tokens": 100})
        self.assertEqual(mock_client.complete.call_count, 11)

    def test_early_exit_when_no_tools_returned(self):
        """Loop exits immediately when the first LLM response has no tool calls."""
        c, mock_client = _bare_compiler([_node_cfg("A", max_tool_calls=5)])
        mock_client.complete.return_value = _text_resp()
        result = c._run_tool_loop(c.nodes["A"], {"temperature": 0.0, "max_tokens": 100})
        # Single call, returns directly — no synthesis step needed
        self.assertEqual(mock_client.complete.call_count, 1)
        self.assertEqual(result.messages, ["final answer"])

    def test_field_parsed_from_config(self):
        """max_tool_calls is correctly parsed from the graph YAML/JSON config."""
        graph = Graph.model_validate(_graph_source(nodes=[_node_cfg("A", max_tool_calls=7)]))
        self.assertEqual(graph.nodes[0].max_tool_calls, 7)

    def test_field_defaults_to_none(self):
        """max_tool_calls defaults to None when omitted from the config."""
        graph = Graph.model_validate(_graph_source(nodes=[_node_cfg("A")]))
        self.assertIsNone(graph.nodes[0].max_tool_calls)


# ===========================================================================
# TestVerboseFlag
# ===========================================================================

class TestVerboseFlag(unittest.TestCase):

    def setUp(self):
        self._log = logging.getLogger("kegal")
        self._saved_level = self._log.level
        self._saved_handlers = list(self._log.handlers)
        self._saved_propagate = self._log.propagate
        # Start each test from a clean logger state
        self._log.handlers.clear()
        self._log.setLevel(logging.WARNING)
        self._log.propagate = True

    def tearDown(self):
        self._log.handlers.clear()
        self._log.handlers.extend(self._saved_handlers)
        self._log.setLevel(self._saved_level)
        self._log.propagate = self._saved_propagate

    def _source(self, verbose: bool) -> dict:
        return _graph_source(verbose=verbose)

    def test_verbose_true_sets_info_level(self):
        """verbose=true must promote the kegal logger to INFO."""
        with patch("kegal.compiler.LlmHandler", return_value=MagicMock()):
            Compiler(source=self._source(verbose=True))
        self.assertEqual(self._log.level, logging.INFO)

    def test_verbose_true_adds_stream_handler(self):
        """verbose=true must attach a StreamHandler to the kegal logger."""
        with patch("kegal.compiler.LlmHandler", return_value=MagicMock()):
            Compiler(source=self._source(verbose=True))
        self.assertTrue(
            any(isinstance(h, logging.StreamHandler) for h in self._log.handlers)
        )

    def test_verbose_true_disables_propagation(self):
        """verbose=true must set propagate=False to prevent duplicate root-logger output."""
        with patch("kegal.compiler.LlmHandler", return_value=MagicMock()):
            Compiler(source=self._source(verbose=True))
        self.assertFalse(self._log.propagate)

    def test_verbose_false_does_not_touch_logger(self):
        """verbose=false must leave the kegal logger at its default state."""
        with patch("kegal.compiler.LlmHandler", return_value=MagicMock()):
            Compiler(source=self._source(verbose=False))
        self.assertEqual(self._log.level, logging.WARNING)
        self.assertEqual(self._log.handlers, [])

    def test_verbose_parsed_from_graph_config(self):
        """verbose field is correctly parsed by the Graph Pydantic model."""
        self.assertTrue(Graph.model_validate(self._source(verbose=True)).verbose)
        self.assertFalse(Graph.model_validate(self._source(verbose=False)).verbose)

    def test_second_compiler_does_not_add_duplicate_handler(self):
        """A second verbose Compiler must not add a second StreamHandler."""
        with patch("kegal.compiler.LlmHandler", return_value=MagicMock()):
            Compiler(source=self._source(verbose=True))
            count_after_first = len(self._log.handlers)
            Compiler(source=self._source(verbose=True))
        self.assertEqual(len(self._log.handlers), count_after_first)


# ===========================================================================
# TestNodeMcpServerRefTools
# ===========================================================================

class TestNodeMcpServerRefTools(unittest.TestCase):

    # --- Pydantic model / parsing ---

    def test_string_normalises_to_ref(self):
        """A plain string is normalised to NodeMcpServerRef(id=..., tools=None)."""
        graph = Graph.model_validate(_graph_source(nodes=[{
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 100,
            "show": False, "prompt": {"template": 0},
            "mcp_servers": ["file_tools"],
        }]))
        ref = graph.nodes[0].mcp_servers[0]
        self.assertIsInstance(ref, NodeMcpServerRef)
        self.assertEqual(ref.id, "file_tools")
        self.assertIsNone(ref.tools)

    def test_object_form_parsed_correctly(self):
        """Object form with tools whitelist is parsed into a NodeMcpServerRef."""
        graph = Graph.model_validate(_graph_source(nodes=[{
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 100,
            "show": False, "prompt": {"template": 0},
            "mcp_servers": [{"id": "file_tools", "tools": ["read", "write"]}],
        }]))
        ref = graph.nodes[0].mcp_servers[0]
        self.assertEqual(ref.id, "file_tools")
        self.assertEqual(ref.tools, ["read", "write"])

    def test_mixed_string_and_object_form(self):
        """String and object forms can be mixed in the same mcp_servers list."""
        graph = Graph.model_validate(_graph_source(nodes=[{
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 100,
            "show": False, "prompt": {"template": 0},
            "mcp_servers": ["srv_a", {"id": "srv_b", "tools": ["search"]}],
        }]))
        refs = graph.nodes[0].mcp_servers
        self.assertEqual(refs[0].id, "srv_a")
        self.assertIsNone(refs[0].tools)
        self.assertEqual(refs[1].id, "srv_b")
        self.assertEqual(refs[1].tools, ["search"])

    def test_empty_tools_list_raises(self):
        """tools=[] is invalid; must be None or a non-empty list."""
        with self.assertRaises(ValidationError):
            Graph.model_validate(_graph_source(nodes=[{
                "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 100,
                "show": False, "prompt": {"template": 0},
                "mcp_servers": [{"id": "srv", "tools": []}],
            }]))

    # --- Tool collection filtering (_mcp_tools_for_node) ---

    def _compiler_with_mock_mcp(self, tools_whitelist=None) -> Compiler:
        """Bare compiler with one MCP server exposing read / write / delete."""
        mcp_servers_cfg = (
            [{"id": "srv", "tools": tools_whitelist}]
            if tools_whitelist is not None
            else ["srv"]
        )
        c, _ = _bare_compiler(nodes_cfg=[{
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 100,
            "show": False, "prompt": {"template": 0},
            "mcp_servers": mcp_servers_cfg,
        }])
        fake_tools = [
            LLMTool(name="read",   description="read a file",   parameters={}, required=[]),
            LLMTool(name="write",  description="write a file",  parameters={}, required=[]),
            LLMTool(name="delete", description="delete a file", parameters={}, required=[]),
        ]
        mock_handler = MagicMock()
        mock_handler.list_tools.return_value = fake_tools
        mock_handler.tool_names.return_value = [t.name for t in fake_tools]
        c.mcp_handlers = {"srv": mock_handler}
        return c

    def test_no_whitelist_exposes_all_tools(self):
        """tools=None must pass through all server tools unchanged."""
        c = self._compiler_with_mock_mcp(tools_whitelist=None)
        names = [t.name for t in c._mcp_tools_for_node(c.nodes["n"])]
        self.assertEqual(sorted(names), ["delete", "read", "write"])

    def test_whitelist_filters_tools(self):
        """tools=[read, write] must exclude 'delete' from the node's tool list."""
        c = self._compiler_with_mock_mcp(tools_whitelist=["read", "write"])
        names = [t.name for t in c._mcp_tools_for_node(c.nodes["n"])]
        self.assertIn("read", names)
        self.assertIn("write", names)
        self.assertNotIn("delete", names)

    def test_whitelist_single_tool(self):
        """A single-entry whitelist exposes exactly one tool."""
        c = self._compiler_with_mock_mcp(tools_whitelist=["read"])
        tools = c._mcp_tools_for_node(c.nodes["n"])
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "read")

    # --- Dispatch guard (_mcp_server_for_tool) ---

    def test_dispatch_blocked_for_non_whitelisted_tool(self):
        """Calling a tool not in the whitelist must return None (not routed)."""
        c = self._compiler_with_mock_mcp(tools_whitelist=["read"])
        self.assertIsNone(c._mcp_server_for_tool("delete", c.nodes["n"]))

    def test_dispatch_allowed_for_whitelisted_tool(self):
        """Calling a whitelisted tool must return the MCP handler."""
        c = self._compiler_with_mock_mcp(tools_whitelist=["read", "write"])
        self.assertIsNotNone(c._mcp_server_for_tool("read", c.nodes["n"]))

    def test_dispatch_allowed_when_no_whitelist(self):
        """With tools=None any server tool is routed normally."""
        c = self._compiler_with_mock_mcp(tools_whitelist=None)
        self.assertIsNotNone(c._mcp_server_for_tool("delete", c.nodes["n"]))


# ===========================================================================
# TestPythonToolExecutor
# ===========================================================================

class TestPythonToolExecutor(unittest.TestCase):
    """Tests for _execute_tool_call and tool loop behaviour with Python executors."""

    def _compiler_with_executor(self, executors: dict) -> tuple:
        """Bare compiler with the given Python tool executors and a mocked LLM."""
        c, mock_client = _bare_compiler()
        c.tool_executors = executors
        return c, mock_client

    # --- _execute_tool_call ---

    def test_executor_called_with_correct_kwargs(self):
        """_execute_tool_call passes parameters as keyword arguments to the function."""
        received = {}

        def my_tool(city: str, units: str) -> str:
            received.update({"city": city, "units": units})
            return "ok"

        c, _ = self._compiler_with_executor({"my_tool": my_tool})
        c._execute_tool_call("my_tool", {"city": "Rome", "units": "C"}, c.nodes["n"])
        self.assertEqual(received, {"city": "Rome", "units": "C"})

    def test_executor_return_value_stringified(self):
        """_execute_tool_call converts any return type to str."""
        c, _ = self._compiler_with_executor({"num": lambda: 42})
        result = c._execute_tool_call("num", {}, c.nodes["n"])
        self.assertIsInstance(result, str)
        self.assertEqual(result, "42")

    def test_unregistered_tool_raises_runtime_error(self):
        """Calling a tool with no registered executor raises RuntimeError."""
        c, _ = self._compiler_with_executor({})
        with self.assertRaises(RuntimeError) as ctx:
            c._execute_tool_call("ghost_tool", {}, c.nodes["n"])
        self.assertIn("ghost_tool", str(ctx.exception))

    def test_mcp_takes_priority_over_python_executor(self):
        """When both MCP and Python executor exist for the same name, MCP wins."""
        python_called = []
        c, _ = self._compiler_with_executor({"shared": lambda: python_called.append(True) or "py"})

        mock_handler = MagicMock()
        mock_handler.call_tool.return_value = "mcp"
        mock_handler.tool_names.return_value = ["shared"]
        c.mcp_handlers = {"srv": mock_handler}

        from kegal.graph_node import NodeMcpServerRef
        c.nodes["n"].mcp_servers = [NodeMcpServerRef(id="srv")]

        result = c._execute_tool_call("shared", {}, c.nodes["n"])
        self.assertEqual(result, "mcp")
        self.assertEqual(python_called, [])

    # --- tool loop integration ---

    def test_tool_results_accumulated_in_response(self):
        """After one tool call, response.tool_results contains the tool output."""
        c, mock_client = self._compiler_with_executor(
            {"say_hi": lambda name: f"Hi {name}"}
        )
        mock_client.complete.side_effect = [
            LLmResponse(tools=[LLMFunctionCall(name="say_hi", parameters={"name": "Alice"})],
                        input_size=10),
            LLmResponse(messages=["done"], input_size=20),
        ]
        resp = c._run_tool_loop(c.nodes["n"], {"temperature": 0.0, "max_tokens": 100})
        self.assertIsNotNone(resp.tool_results)
        self.assertIn("Hi Alice", resp.tool_results[0])

    def test_tool_call_injected_into_next_llm_call_history(self):
        """After a tool call, the second LLM call receives the call+result in history."""
        c, mock_client = self._compiler_with_executor({"echo": lambda x: x})
        mock_client.complete.side_effect = [
            LLmResponse(tools=[LLMFunctionCall(name="echo", parameters={"x": "hello"})],
                        input_size=10),
            LLmResponse(messages=["done"], input_size=20),
        ]
        c._run_tool_loop(c.nodes["n"], {"temperature": 0.0, "max_tokens": 100})

        second_call_kwargs = mock_client.complete.call_args_list[1][1]
        history = second_call_kwargs.get("chat_history", [])
        history_text = " ".join(m.content for m in history)
        self.assertIn("echo", history_text)
        self.assertIn("hello", history_text)

    def test_multiple_tool_calls_in_one_response_all_executed(self):
        """Multiple tool calls returned by a single LLM response are all executed."""
        call_log = []

        def tracker(label: str) -> str:
            call_log.append(label)
            return label

        c, mock_client = self._compiler_with_executor({"track": tracker})
        mock_client.complete.side_effect = [
            LLmResponse(
                tools=[
                    LLMFunctionCall(name="track", parameters={"label": "a"}),
                    LLMFunctionCall(name="track", parameters={"label": "b"}),
                    LLMFunctionCall(name="track", parameters={"label": "c"}),
                ],
                input_size=10,
            ),
            LLmResponse(messages=["done"], input_size=20),
        ]
        c._run_tool_loop(c.nodes["n"], {"temperature": 0.0, "max_tokens": 100})
        self.assertEqual(sorted(call_log), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
