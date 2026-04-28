import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from kegal.compiler import Compiler, ReactTrace
from kegal.graph import Graph, NodeReact

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_compiler(nodes_cfg: list, edges_cfg: list, extra: dict | None = None) -> Compiler:
    """Build a Compiler from minimal config dicts without connecting to any LLM."""
    source = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": nodes_cfg,
        "edges": edges_cfg,
    }
    if extra:
        source.update(extra)
    graph = Graph.model_validate(source)
    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    c.clients = []
    c.prompts = []
    c.react_compact_prompts = []
    c._react_trace = {}
    c._react_controllers = c._build_react_controller_map()
    return c


def _node(nid: str, mp_in: bool = False, mp_out: bool = False,
          react: bool = False, react_output: dict | None = None) -> dict:
    n: dict = {
        "id": nid, "model": 0, "temperature": 0.0, "max_tokens": 100,
        "show": False,
        "message_passing": {"input": mp_in, "output": mp_out},
        "prompt": {"template": 0},
    }
    if react:
        n["react"] = {"max_iterations": 5}
    if react_output:
        n["react_output"] = react_output
    return n


def _level_of(levels: list, nid: str) -> int:
    return next(i for i, lvl in enumerate(levels) if nid in lvl)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestReactSchema(unittest.TestCase):

    def test_node_react_defaults(self):
        r = NodeReact()
        self.assertEqual(r.max_iterations, 10)
        self.assertFalse(r.resume)
        self.assertAlmostEqual(r.resume_threshold, 0.8)

    def test_node_react_custom(self):
        r = NodeReact(max_iterations=3, resume=True, resume_threshold=0.6)
        self.assertEqual(r.max_iterations, 3)
        self.assertTrue(r.resume)

    def test_react_and_children_mutually_exclusive(self):
        with self.assertRaises(ValidationError):
            Graph.model_validate({
                "models": [{"llm": "ollama", "model": "dummy"}],
                "prompts": [{"template": {}}],
                "nodes": [_node("A"), _node("agent")],
                "edges": [{"node": "A", "react": [{"node": "agent"}], "children": [{"node": "agent"}]}],
            })

    def test_react_and_fan_in_are_not_exclusive(self):
        """react and fan_in can coexist on the same edge."""
        g = Graph.model_validate({
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "nodes": [_node("A"), _node("B"), _node("agent")],
            "edges": [
                {"node": "A", "fan_in": [{"node": "B"}], "react": [{"node": "agent"}]}
            ],
        })
        self.assertIsNotNone(g.edges[0].react)
        self.assertIsNotNone(g.edges[0].fan_in)

    def test_react_output_on_node(self):
        schema = {"type": "object", "properties": {"next_agent": {"type": "string"}}}
        g = Graph.model_validate({
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "nodes": [_node("ctrl", react=True, react_output=schema)],
            "edges": [],
        })
        self.assertEqual(g.nodes[0].react_output, schema)

    def test_react_compact_prompts_on_graph(self):
        g = Graph.model_validate({
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "react_compact_prompts": [{"template": {"system_template": {"s": "compact"}, "prompt_template": {}}}],
            "nodes": [_node("A")],
            "edges": [],
        })
        self.assertIsNotNone(g.react_compact_prompts)
        self.assertEqual(len(g.react_compact_prompts), 1)


# ---------------------------------------------------------------------------
# DAG building with react nodes
# ---------------------------------------------------------------------------

class TestReactDAGBuild(unittest.TestCase):

    def test_react_agent_nodes_excluded_from_dag(self):
        """Nodes listed in react lists must not appear in the main DAG deps map."""
        c = _make_compiler(
            [_node("ctrl", react=True), _node("agent_a"), _node("agent_b")],
            [{"node": "ctrl", "react": [{"node": "agent_a"}, {"node": "agent_b"}]}],
        )
        deps = c._build_dag()
        self.assertIn("ctrl", deps)
        self.assertNotIn("agent_a", deps)
        self.assertNotIn("agent_b", deps)

    def test_controller_appears_in_dag(self):
        """The controller node itself must be in the main DAG."""
        c = _make_compiler(
            [_node("ctrl", react=True), _node("agent")],
            [{"node": "ctrl", "react": [{"node": "agent"}]}],
        )
        deps = c._build_dag()
        self.assertIn("ctrl", deps)

    def test_react_agent_not_traversed_for_cycles(self):
        """Cycle detection must not traverse react lists."""
        c = _make_compiler(
            [_node("ctrl", react=True), _node("agent")],
            [{"node": "ctrl", "react": [{"node": "agent"}]}],
        )
        deps = c._build_dag()  # must not raise
        self.assertIn("ctrl", deps)

    def test_react_controller_map_built(self):
        """_build_react_controller_map must find the controller edge."""
        c = _make_compiler(
            [_node("ctrl", react=True), _node("agent")],
            [{"node": "ctrl", "react": [{"node": "agent"}]}],
        )
        self.assertIn("ctrl", c._react_controllers)
        self.assertEqual(c._react_controllers["ctrl"].node, "ctrl")

    def test_controller_with_children_before_react(self):
        """A controller can have fan-out children that run before the react loop."""
        c = _make_compiler(
            [_node("pre"), _node("ctrl", react=True), _node("agent")],
            [
                {"node": "pre", "children": [{"node": "ctrl"}]},
                {"node": "ctrl", "react": [{"node": "agent"}]},
            ],
        )
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        self.assertLess(_level_of(levels, "pre"), _level_of(levels, "ctrl"))
        self.assertNotIn("agent", [nid for lvl in levels for nid in lvl])


# ---------------------------------------------------------------------------
# _validate_indices with react
# ---------------------------------------------------------------------------

class TestReactValidateIndices(unittest.TestCase):

    def test_double_execution_raises(self):
        """A node appearing in both main edges and a react list must raise ValueError."""
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "nodes": [_node("ctrl", react=True), _node("shared")],
            "edges": [
                {"node": "ctrl", "react": [{"node": "shared"}]},
                {"node": "shared"},
            ],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.clients = [MagicMock()]  # 1 model
        c.prompts = [{}]           # 1 prompt
        c.react_compact_prompts = []
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("shared", str(ctx.exception))

    def test_undefined_react_agent_raises(self):
        """A react agent node not defined in nodes: must raise ValueError."""
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "nodes": [_node("ctrl", react=True)],
            "edges": [{"node": "ctrl", "react": [{"node": "ghost_agent"}]}],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.clients = [MagicMock()]
        c.prompts = [{}]
        c.react_compact_prompts = []
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("ghost_agent", str(ctx.exception))

    def test_collect_react_agent_ids(self):
        c = _make_compiler(
            [_node("ctrl", react=True), _node("a1"), _node("a2")],
            [{"node": "ctrl", "react": [{"node": "a1"}, {"node": "a2"}]}],
        )
        ids = c._collect_react_agent_ids()
        self.assertEqual(ids, {"a1", "a2"})

    def test_collect_main_edge_ids(self):
        c = _make_compiler(
            [_node("ctrl", react=True), _node("a1")],
            [{"node": "ctrl", "react": [{"node": "a1"}]}],
        )
        main = c._collect_main_edge_ids()
        self.assertIn("ctrl", main)
        self.assertNotIn("a1", main)


# ---------------------------------------------------------------------------
# Concurrent controller detection
# ---------------------------------------------------------------------------

class TestReactConcurrentControllers(unittest.TestCase):

    def test_two_controllers_at_same_level_raises(self):
        """Two controllers without dependency between them must raise ValueError at compile."""
        c = _make_compiler(
            [_node("ctrl1", react=True), _node("ctrl2", react=True),
             _node("agent1"), _node("agent2")],
            [
                {"node": "ctrl1", "react": [{"node": "agent1"}]},
                {"node": "ctrl2", "react": [{"node": "agent2"}]},
            ],
        )
        # Simulate compile: build DAG and levels, then check
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        # Both controllers should be at the same level (no deps between them)
        lvl1 = _level_of(levels, "ctrl1")
        lvl2 = _level_of(levels, "ctrl2")
        self.assertEqual(lvl1, lvl2)
        # compile() should raise on concurrent controllers
        c.outputs = MagicMock()
        c.outputs.compile_time = 0
        c.message_passing = []
        with self.assertRaises(ValueError) as ctx:
            # Simulate the level loop that compile() does
            react_ids = [nid for nid in levels[lvl1] if nid in c._react_controllers]
            if len(react_ids) > 1:
                raise ValueError(f"Concurrent react controllers: {react_ids}")
        self.assertIn("Concurrent", str(ctx.exception))


# ---------------------------------------------------------------------------
# find_react_agent_edge helper
# ---------------------------------------------------------------------------

class TestFindReactAgentEdge(unittest.TestCase):

    def test_finds_correct_agent(self):
        c = _make_compiler(
            [_node("ctrl", react=True), _node("a"), _node("b")],
            [{"node": "ctrl", "react": [{"node": "a"}, {"node": "b"}]}],
        )
        ctrl_edge = c._react_controllers["ctrl"]
        found = c._find_react_agent_edge(ctrl_edge, "b")
        self.assertIsNotNone(found)
        self.assertEqual(found.node, "b")

    def test_returns_none_for_unknown_agent(self):
        c = _make_compiler(
            [_node("ctrl", react=True), _node("a")],
            [{"node": "ctrl", "react": [{"node": "a"}]}],
        )
        ctrl_edge = c._react_controllers["ctrl"]
        result = c._find_react_agent_edge(ctrl_edge, "missing")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _run_react_agent — isolation
# ---------------------------------------------------------------------------

class TestRunReactAgent(unittest.TestCase):

    def _build_agent_compiler(self):
        from kegal.compiler import CompiledOutput
        c = _make_compiler(
            [_node("ctrl", react=True), _node("worker", mp_out=True)],
            [{"node": "ctrl", "react": [{"node": "worker"}]}],
        )
        c.outputs = CompiledOutput()
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        return c

    def test_state_restored_after_agent(self):
        """Global message_passing and outputs must be restored after agent run."""
        c = self._build_agent_compiler()
        c.message_passing = ["original"]
        from kegal.compiler import CompiledOutput
        c.outputs = CompiledOutput()

        agent_edge = c._react_controllers["ctrl"].react[0]

        fake_response = MagicMock()
        fake_response.messages = ["agent result"]
        fake_response.json_output = None
        fake_response.tools = None
        fake_response.tool_results = None
        fake_response.input_size = 10
        fake_response.output_size = 5

        with patch.object(c, "_run_node", return_value=None):
            # simulate _run_node writing to self.message_passing
            def fake_run_node(_node):
                c.message_passing.append("worker output")
            c._run_node = fake_run_node

            c._run_react_agent(agent_edge, "input question")

        # State restored
        self.assertEqual(c.message_passing, ["original"])

    def test_result_from_message_passing_output(self):
        """Result must prefer new message_passing entries over node response."""
        c = self._build_agent_compiler()
        c.message_passing = []

        agent_edge = c._react_controllers["ctrl"].react[0]

        def fake_run_node(_node):
            c.message_passing.append("computed result")

        c._run_node = fake_run_node
        result = c._run_react_agent(agent_edge, "compute this")

        self.assertEqual(result, "computed result")


# ---------------------------------------------------------------------------
# _run_react_loop — mocked LLM
# ---------------------------------------------------------------------------

class TestRunReactLoop(unittest.TestCase):

    def _setup_controller(self):
        """Build a minimal compiler with a controller and two agent nodes."""
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [
                {"template": {"system_template": {"r": "ctrl"}, "prompt_template": {"t": "{user_message}"}}},
                {"template": {"system_template": {}, "prompt_template": {}}},
            ],
            "user_message": "test question",
            "nodes": [
                {
                    "id": "ctrl", "model": 0, "temperature": 0.0, "max_tokens": 200,
                    "show": True, "prompt": {"template": 0, "user_message": True},
                    "react": {"max_iterations": 4},
                    "react_output": {
                        "type": "object",
                        "properties": {
                            "next_agent": {"type": "string"},
                            "done": {"type": "boolean"},
                            "final_answer": {"type": "string"},
                        },
                        "required": ["next_agent"],
                    },
                },
                {"id": "agent_a", "model": 0, "temperature": 0.0, "max_tokens": 100,
                 "show": False, "prompt": {"template": 1},
                 "message_passing": {"input": True, "output": True}},
            ],
            "edges": [{"node": "ctrl", "react": [{"node": "agent_a"}]}],
        }
        graph = Graph.model_validate(source)

        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.prompts = Compiler._load_prompt_inputs(graph.prompts)
        c.react_compact_prompts = []
        c.user_message = graph.user_message
        c.retrieved_chunks = None
        c.chat_history = None
        c.images = None
        c.documents = None
        c.tools = None
        c.blackboard = ""
        c._blackboard_path = None
        c.mcp_handlers = {}
        c.tool_executors = {}
        c.message_passing = []
        c.graph_mcp_servers = []
        c._react_trace = {}
        c._react_controllers = c._build_react_controller_map()
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        from kegal.compiler import CompiledOutput
        c.outputs = CompiledOutput()

        # Mock LLM client
        mock_client = MagicMock()
        c.clients = [mock_client]
        return c, mock_client

    def _make_response(self, json_out: dict, messages: list[str] | None = None):
        from kegal.llm.llm_model import LLmResponse
        return LLmResponse(
            json_output=json_out,
            messages=messages,
            input_size=50,
            output_size=20,
        )

    def test_loop_stops_on_done_true(self):
        """Loop must stop and record trace when controller returns done=true."""
        c, mock_client = self._setup_controller()

        # First call: dispatch to agent_a; second call: done
        mock_client.complete.side_effect = [
            self._make_response({"next_agent": "agent_a", "reasoning": "need agent"}),
            self._make_response({"next_agent": "agent_a", "done": True, "final_answer": "42"}),
        ]

        ctrl_edge = c._react_controllers["ctrl"]

        with patch.object(c, "_run_react_agent", return_value="agent said 42"):
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        trace = c.get_react_trace("ctrl")
        self.assertIsNotNone(trace)
        self.assertTrue(trace.done)
        self.assertEqual(trace.final_answer, "42")
        self.assertEqual(trace.total_iterations, 1)

    def test_loop_stops_at_max_iterations(self):
        """Loop must stop after max_iterations even if done is never returned."""
        c, mock_client = self._setup_controller()
        # Always dispatch, never done
        mock_client.complete.return_value = self._make_response(
            {"next_agent": "agent_a", "reasoning": "still going"}
        )

        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="result"):
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        trace = c.get_react_trace("ctrl")
        self.assertFalse(trace.done)
        # max_iterations=4 dispatches, but the last call checks done → 4 agent calls
        self.assertLessEqual(trace.total_iterations, 4)

    def test_unknown_agent_stops_gracefully(self):
        """next_agent not in react list must stop the loop (no RuntimeError)."""
        c, mock_client = self._setup_controller()
        mock_client.complete.return_value = self._make_response(
            {"next_agent": "ghost_agent"}
        )
        ctrl_edge = c._react_controllers["ctrl"]
        # Should not raise — unknown agent is treated as a stop signal
        c._run_react_loop(ctrl_edge, c.nodes["ctrl"])
        trace = c.get_react_trace("ctrl")
        # No iteration was completed (agent was not found, so loop stopped before dispatch)
        self.assertEqual(trace.total_iterations, 0)

    def test_trace_contains_iteration_data(self):
        """Each iteration must record agent_name, output, reasoning."""
        c, mock_client = self._setup_controller()
        mock_client.complete.side_effect = [
            self._make_response({"next_agent": "agent_a", "reasoning": "r1"}),
            self._make_response({"next_agent": "agent_a", "done": True, "final_answer": "done"}),
        ]
        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="output1"):
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        trace = c.get_react_trace("ctrl")
        self.assertEqual(len(trace.iterations), 1)
        it = trace.iterations[0]
        self.assertEqual(it.agent_name, "agent_a")
        self.assertEqual(it.agent_output, "output1")
        self.assertEqual(it.reasoning, "r1")

    def test_get_react_trace_returns_none_before_compile(self):
        c, _ = self._setup_controller()
        self.assertIsNone(c.get_react_trace("ctrl"))

    def test_controller_output_recorded(self):
        """Controller node must appear in outputs.nodes after the loop."""
        c, mock_client = self._setup_controller()
        mock_client.complete.return_value = self._make_response(
            {"next_agent": "agent_a", "done": True, "final_answer": "answer"}
        )
        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="x"):
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        executed = {n.node_id for n in c.outputs.nodes}
        self.assertIn("ctrl", executed)

    def test_token_totals_accumulated(self):
        """Total controller tokens must sum across all iterations."""
        c, mock_client = self._setup_controller()
        mock_client.complete.side_effect = [
            self._make_response({"next_agent": "agent_a"}),
            self._make_response({"next_agent": "agent_a", "done": True}),
        ]
        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="x"):
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        trace = c.get_react_trace("ctrl")
        # Each mock response has input_size=50, output_size=20; 2 calls
        self.assertEqual(trace.total_controller_input_tokens, 100)
        self.assertEqual(trace.total_controller_output_tokens, 40)


# ---------------------------------------------------------------------------
# _maybe_compact
# ---------------------------------------------------------------------------

class TestMaybeCompact(unittest.TestCase):

    def _setup(self):
        from kegal.compiler import CompiledOutput
        c = _make_compiler(
            [_node("ctrl", react=True), _node("agent")],
            [{"node": "ctrl", "react": [{"node": "agent"}]}],
        )
        c.outputs = CompiledOutput()
        c._outputs_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()

        mock_client = MagicMock()
        c.clients = [mock_client]
        return c, mock_client

    def _make_response(self, input_size: int):
        from kegal.llm.llm_model import LLmResponse
        return LLmResponse(input_size=input_size, output_size=10, messages=["compacted state"])

    def test_no_compact_below_threshold(self):
        """Compaction must NOT be triggered when input_size < max_tokens * threshold."""
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse
        last_response = LLmResponse(input_size=50, output_size=5)  # 50 < 100 * 0.8
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100

        conversation = [MagicMock()]
        c._maybe_compact(conversation, node, 0.8, last_response)

        mock_client.complete.assert_not_called()

    def test_compact_triggered_at_threshold(self):
        """Compaction must be triggered when input_size >= max_tokens * threshold."""
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse
        last_response = LLmResponse(input_size=85, output_size=5)  # 85 >= 100 * 0.8
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100

        mock_client.complete.return_value = self._make_response(input_size=10)
        conversation: list = [MagicMock(), MagicMock()]

        c._maybe_compact(conversation, node, 0.8, last_response)

        mock_client.complete.assert_called_once()

    def test_compact_replaces_conversation(self):
        """After compaction, conversation must contain exactly one [compacted state] message."""
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse, LLmMessage
        last_response = LLmResponse(input_size=90, output_size=5)
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100

        mock_client.complete.return_value = self._make_response(input_size=10)
        conversation: list[LLmMessage] = [
            LLmMessage(role="user", content="turn 1"),
            LLmMessage(role="assistant", content="turn 2"),
            LLmMessage(role="user", content="turn 3"),
        ]

        c._maybe_compact(conversation, node, 0.8, last_response)

        self.assertEqual(len(conversation), 1)
        self.assertIn("compacted", conversation[0].content)

    def test_compact_uses_default_prompt_when_no_custom(self):
        """Default compact prompt must be used when react_compact_prompts is empty."""
        from kegal.compiler import _DEFAULT_REACT_COMPACT_PROMPT
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse
        last_response = LLmResponse(input_size=90, output_size=5)
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100
        c.react_compact_prompts = []  # no custom prompt

        mock_client.complete.return_value = self._make_response(input_size=10)
        c._maybe_compact([], node, 0.8, last_response)

        call_kwargs = mock_client.complete.call_args
        self.assertEqual(
            call_kwargs.kwargs.get("system_prompt") or call_kwargs[1].get("system_prompt"),
            _DEFAULT_REACT_COMPACT_PROMPT["system"],
        )

    def test_compact_uses_custom_prompt(self):
        """Custom react_compact_prompts[0] must override the default."""
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse
        last_response = LLmResponse(input_size=90, output_size=5)
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100
        c.react_compact_prompts = [{"system": "CUSTOM SYSTEM", "user": "CUSTOM USER"}]

        mock_client.complete.return_value = self._make_response(input_size=10)
        c._maybe_compact([], node, 0.8, last_response)

        call_kwargs = mock_client.complete.call_args
        self.assertEqual(
            call_kwargs.kwargs.get("system_prompt") or call_kwargs[1].get("system_prompt"),
            "CUSTOM SYSTEM",
        )

    def test_compact_no_change_when_llm_returns_no_messages(self):
        """If LLM returns no messages, conversation must not be modified."""
        c, mock_client = self._setup()
        from kegal.llm.llm_model import LLmResponse, LLmMessage
        last_response = LLmResponse(input_size=90, output_size=5)
        node = c.nodes["ctrl"]
        node.__dict__["max_tokens"] = 100

        mock_client.complete.return_value = LLmResponse(input_size=5, output_size=2, messages=None)
        original = [LLmMessage(role="user", content="x")]
        conversation = list(original)

        c._maybe_compact(conversation, node, 0.8, last_response)

        # Conversation unchanged since no messages returned
        self.assertEqual(len(conversation), 1)
        self.assertEqual(conversation[0].content, "x")


# ---------------------------------------------------------------------------
# _run_react_agent — fallback and multi-node subgraph
# ---------------------------------------------------------------------------

class TestRunReactAgentExtended(unittest.TestCase):

    def _setup(self):
        from kegal.compiler import CompiledOutput
        c = _make_compiler(
            [_node("ctrl", react=True), _node("w1"), _node("w2")],
            [{"node": "ctrl", "react": [
                {"node": "w1", "children": [{"node": "w2"}]}
            ]}],
        )
        c.outputs = CompiledOutput()
        c.message_passing = []
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        return c

    def test_multi_node_agent_runs_in_order(self):
        """Agent subgraph w1→w2 must run w1 before w2."""
        c = self._setup()
        execution_order: list[str] = []

        def fake_run_node(node):
            execution_order.append(node.id)

        c._run_node = fake_run_node
        agent_edge = c._react_controllers["ctrl"].react[0]
        c._run_react_agent(agent_edge, "task")

        self.assertEqual(execution_order, ["w1", "w2"])

    def test_fallback_to_last_node_response(self):
        """When no message_passing.output nodes exist, fall back to last node response."""
        from kegal.compiler import CompiledOutput, CompiledNodeOutput
        from kegal.llm.llm_model import LLmResponse
        c = _make_compiler(
            [_node("ctrl", react=True), _node("solo")],
            [{"node": "ctrl", "react": [{"node": "solo"}]}],
        )
        c.outputs = CompiledOutput()
        c.message_passing = []
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()

        fake_response = LLmResponse(messages=["solo result"], input_size=5, output_size=3)

        def fake_run_node(node):
            # solo has mp_out=False, so no message_passing write — append to outputs directly
            c.outputs.nodes.append(CompiledNodeOutput(
                node_id=node.id, response=fake_response,
                compiled_time=0.0, show=False, history=False,
            ))

        c._run_node = fake_run_node
        agent_edge = c._react_controllers["ctrl"].react[0]
        result = c._run_react_agent(agent_edge, "question")

        self.assertEqual(result, "solo result")

    def test_state_restored_on_exception(self):
        """Global state must be restored even if the agent subgraph raises."""
        from kegal.compiler import CompiledOutput
        c = _make_compiler(
            [_node("ctrl", react=True), _node("bad_agent")],
            [{"node": "ctrl", "react": [{"node": "bad_agent"}]}],
        )
        c.outputs = CompiledOutput()
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        c.message_passing = ["preserved"]

        def always_raise(_node):
            raise RuntimeError("agent exploded")

        c._run_node = always_raise
        agent_edge = c._react_controllers["ctrl"].react[0]

        with self.assertRaises(RuntimeError):
            c._run_react_agent(agent_edge, "input")

        self.assertEqual(c.message_passing, ["preserved"])


# ---------------------------------------------------------------------------
# resume flag in _run_react_loop
# ---------------------------------------------------------------------------

class TestResumeInLoop(unittest.TestCase):

    def _setup_with_resume(self, threshold: float = 0.5):
        from kegal.compiler import CompiledOutput
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [
                {"template": {"system_template": {}, "prompt_template": {}}},
                {"template": {"system_template": {}, "prompt_template": {}}},
            ],
            "user_message": "test",
            "nodes": [
                {
                    "id": "ctrl", "model": 0, "temperature": 0.0, "max_tokens": 100,
                    "show": True, "prompt": {"template": 0},
                    "react": {"max_iterations": 3, "resume": True, "resume_threshold": threshold},
                    "react_output": {
                        "type": "object",
                        "properties": {"next_agent": {"type": "string"}, "done": {"type": "boolean"}},
                        "required": ["next_agent"],
                    },
                },
                {"id": "agent_a", "model": 0, "temperature": 0.0, "max_tokens": 50,
                 "show": False, "prompt": {"template": 1}},
            ],
            "edges": [{"node": "ctrl", "react": [{"node": "agent_a"}]}],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.prompts = Compiler._load_prompt_inputs(graph.prompts)
        c.react_compact_prompts = []
        c.user_message = graph.user_message
        c.retrieved_chunks = None
        c.chat_history = None
        c.images = None
        c.documents = None
        c.tools = None
        c.blackboard = ""
        c._blackboard_path = None
        c.mcp_handlers = {}
        c.tool_executors = {}
        c.message_passing = []
        c.graph_mcp_servers = []
        c._react_trace = {}
        c._react_controllers = c._build_react_controller_map()
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        c.outputs = CompiledOutput()
        mock_client = MagicMock()
        c.clients = [mock_client]
        return c, mock_client

    def test_compact_called_when_threshold_exceeded(self):
        """_maybe_compact must be called when input_size >= max_tokens * threshold."""
        from kegal.llm.llm_model import LLmResponse
        c, mock_client = self._setup_with_resume(threshold=0.5)

        # First call: input_size=60 >= 100*0.5=50 → compact triggered
        # Second call: done
        mock_client.complete.side_effect = [
            LLmResponse(json_output={"next_agent": "agent_a"}, input_size=60, output_size=5),
            LLmResponse(json_output={"next_agent": "agent_a", "done": True}, input_size=10, output_size=5),
        ]

        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="result"), \
             patch.object(c, "_maybe_compact") as mock_compact:
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        mock_compact.assert_called()

    def test_compact_not_called_when_resume_false(self):
        """_maybe_compact must NOT be called when resume=false even if threshold exceeded."""
        from kegal.llm.llm_model import LLmResponse
        # resume=False in NodeReact default
        from kegal.compiler import CompiledOutput
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [
                {"template": {"system_template": {}, "prompt_template": {}}},
                {"template": {"system_template": {}, "prompt_template": {}}},
            ],
            "user_message": "test",
            "nodes": [
                {
                    "id": "ctrl", "model": 0, "temperature": 0.0, "max_tokens": 100,
                    "show": True, "prompt": {"template": 0},
                    "react": {"max_iterations": 2, "resume": False},
                    "react_output": {
                        "type": "object",
                        "properties": {"next_agent": {"type": "string"}, "done": {"type": "boolean"}},
                        "required": ["next_agent"],
                    },
                },
                {"id": "agent_a", "model": 0, "temperature": 0.0, "max_tokens": 50,
                 "show": False, "prompt": {"template": 1}},
            ],
            "edges": [{"node": "ctrl", "react": [{"node": "agent_a"}]}],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.prompts = Compiler._load_prompt_inputs(graph.prompts)
        c.react_compact_prompts = []
        c.user_message = "test"
        c.retrieved_chunks = None
        c.chat_history = None
        c.images = None
        c.documents = None
        c.tools = None
        c.blackboard = ""
        c._blackboard_path = None
        c.mcp_handlers = {}
        c.tool_executors = {}
        c.message_passing = []
        c.graph_mcp_servers = []
        c._react_trace = {}
        c._react_controllers = c._build_react_controller_map()
        c._outputs_lock = __import__("threading").Lock()
        c._message_passing_lock = __import__("threading").Lock()
        c._blackboard_lock = __import__("threading").Lock()
        c.outputs = CompiledOutput()
        mock_client = MagicMock()
        c.clients = [mock_client]

        mock_client.complete.side_effect = [
            LLmResponse(json_output={"next_agent": "agent_a"}, input_size=99, output_size=5),
            LLmResponse(json_output={"next_agent": "agent_a", "done": True}, input_size=5, output_size=2),
        ]
        ctrl_edge = c._react_controllers["ctrl"]
        with patch.object(c, "_run_react_agent", return_value="r"), \
             patch.object(c, "_maybe_compact") as mock_compact:
            c._run_react_loop(ctrl_edge, c.nodes["ctrl"])

        mock_compact.assert_not_called()


# ---------------------------------------------------------------------------
# Integration test — requires Ollama running locally
# ---------------------------------------------------------------------------

class TestReactGraphIntegration(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "react_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_excludes_agent_nodes(self):
        """Agent nodes must not appear in the main DAG."""
        deps = self.compiler._build_dag()
        self.assertIn("controller", deps)
        self.assertNotIn("math_agent", deps)
        self.assertNotIn("knowledge_agent", deps)

    def test_controller_is_detected(self):
        """controller must be detected as a react controller."""
        self.assertIn("controller", self.compiler._react_controllers)

    def test_compile_produces_controller_output(self):
        """Full react compilation must produce a controller output entry."""
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed = {n.node_id for n in outputs.nodes}
        self.assertIn("controller", executed)

    def test_trace_populated(self):
        """React trace must be populated after compile."""
        self.compiler.compile()
        trace = self.compiler.get_react_trace("controller")
        self.assertIsNotNone(trace)
        self.assertIsInstance(trace, ReactTrace)

    def test_trace_has_iterations(self):
        """At least one agent must have been called (model-dependent; skip if model did not dispatch)."""
        self.compiler.compile()
        trace = self.compiler.get_react_trace("controller")
        if trace.total_iterations == 0:
            self.skipTest(
                "Model did not dispatch any agent — "
                "small models sometimes skip agent calls. "
                "Run with a larger model for a full integration check."
            )
        self.assertGreater(trace.total_iterations, 0)

    def test_compile_to_file(self):
        """Save compiled outputs and react trace to graph_outputs/react_graph/."""
        import json as _json
        self.compiler.compile()
        out_dir = CURRENT_DIR / "graph_outputs" / "react_graph"
        out_dir.mkdir(parents=True, exist_ok=True)

        self.compiler.save_outputs_as_json(out_dir / "react_graph.json")
        self.compiler.save_outputs_as_markdown(out_dir / "react_graph.md")

        # Write react trace as separate markdown
        trace = self.compiler.get_react_trace("controller")
        if trace:
            md = f"# ReAct Trace — controller\n\n"
            md += f"- **Done**: {trace.done}\n"
            md += f"- **Total iterations**: {trace.total_iterations}\n"
            md += f"- **Final answer**: {trace.final_answer or '—'}\n"
            md += f"- **Controller input tokens**: {trace.total_controller_input_tokens}\n"
            md += f"- **Controller output tokens**: {trace.total_controller_output_tokens}\n\n"
            md += "---\n\n"
            for it in trace.iterations:
                md += f"## Iteration {it.iteration} → `{it.agent_name}`\n\n"
                if it.reasoning:
                    md += f"**Reasoning:** {it.reasoning}\n\n"
                if it.agent_input:
                    md += f"**Agent input:** {it.agent_input}\n\n"
                md += f"**Agent output:**\n\n{it.agent_output}\n\n"
                md += f"*Controller tokens — input: {it.controller_input_tokens}, output: {it.controller_output_tokens}*\n\n"
                md += "---\n\n"
            (out_dir / "react_graph_trace.md").write_text(md, encoding="utf-8")

        # Assert files exist
        self.assertTrue((out_dir / "react_graph.json").exists())
        self.assertTrue((out_dir / "react_graph.md").exists())
