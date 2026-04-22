import logging
import unittest
from pathlib import Path

from pydantic import ValidationError

from kegal.compiler import Compiler
from kegal.graph import Graph

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers shared by edge-system tests
# ---------------------------------------------------------------------------

def _make_compiler(nodes_cfg: list, edges_cfg: list) -> Compiler:
    """Build a Compiler from minimal config dicts without connecting to any LLM."""
    source = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": nodes_cfg,
        "edges": edges_cfg,
    }
    graph = Graph.model_validate(source)
    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    return c


def _node(nid: str, mp_in: bool = False, mp_out: bool = False, guard: bool = False) -> dict:
    n: dict = {
        "id": nid, "model": 0, "temperature": 0.0, "max_tokens": 10,
        "show": False,
        "message_passing": {"input": mp_in, "output": mp_out},
        "prompt": {"template": 0},
    }
    if guard:
        n["structured_output"] = {
            "type": "object",
            "properties": {"validation": {"type": "boolean"}},
        }
    return n


def _level_of(levels: list, nid: str) -> int:
    return next(i for i, lvl in enumerate(levels) if nid in lvl)


# ---------------------------------------------------------------------------
# Edge system — structural / unit tests (no LLM required)
# ---------------------------------------------------------------------------

class TestEdgeSystemFanOut(unittest.TestCase):
    """children: fan-out — parent completes, children start in parallel."""

    def _build(self, nodes, edges):
        c = _make_compiler(nodes, edges)
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        return deps, levels

    def test_children_creates_parent_dependency(self):
        """Each child must depend on its parent."""
        deps, levels = self._build(
            [_node("A"), _node("B"), _node("C"), _node("D")],
            [{"node": "A", "children": [{"node": "B"}, {"node": "C"}, {"node": "D"}]}],
        )
        self.assertIn("A", deps["B"])
        self.assertIn("A", deps["C"])
        self.assertIn("A", deps["D"])

    def test_children_run_at_same_level(self):
        """Siblings with the same parent land at the same topological level."""
        _, levels = self._build(
            [_node("A"), _node("B"), _node("C"), _node("D")],
            [{"node": "A", "children": [{"node": "B"}, {"node": "C"}, {"node": "D"}]}],
        )
        self.assertEqual(
            _level_of(levels, "B"),
            _level_of(levels, "C"),
        )
        self.assertEqual(
            _level_of(levels, "B"),
            _level_of(levels, "D"),
        )

    def test_parent_precedes_children(self):
        """Parent level must be strictly less than children level."""
        _, levels = self._build(
            [_node("A"), _node("B"), _node("C")],
            [{"node": "A", "children": [{"node": "B"}, {"node": "C"}]}],
        )
        self.assertLess(_level_of(levels, "A"), _level_of(levels, "B"))

    def test_deep_chain(self):
        """A → B → C nested children produce three distinct levels."""
        _, levels = self._build(
            [_node("A"), _node("B"), _node("C")],
            [{"node": "A", "children": [{"node": "B", "children": [{"node": "C"}]}]}],
        )
        self.assertLess(_level_of(levels, "A"), _level_of(levels, "B"))
        self.assertLess(_level_of(levels, "B"), _level_of(levels, "C"))


class TestEdgeSystemFanIn(unittest.TestCase):
    """fan_in: aggregation — node waits for all listed nodes."""

    def _build(self, nodes, edges):
        c = _make_compiler(nodes, edges)
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        return deps, levels

    def test_fan_in_creates_dependencies(self):
        """Aggregator must depend on every node in fan_in."""
        deps, _ = self._build(
            [_node("B"), _node("C"), _node("D"), _node("E")],
            [{"node": "E", "fan_in": [{"node": "B"}, {"node": "C"}, {"node": "D"}]}],
        )
        self.assertIn("B", deps["E"])
        self.assertIn("C", deps["E"])
        self.assertIn("D", deps["E"])

    def test_fan_in_sources_precede_aggregator(self):
        """All fan_in source nodes must be at a strictly earlier level than E."""
        _, levels = self._build(
            [_node("B"), _node("C"), _node("D"), _node("E")],
            [{"node": "E", "fan_in": [{"node": "B"}, {"node": "C"}, {"node": "D"}]}],
        )
        e_lvl = _level_of(levels, "E")
        self.assertLess(_level_of(levels, "B"), e_lvl)
        self.assertLess(_level_of(levels, "C"), e_lvl)
        self.assertLess(_level_of(levels, "D"), e_lvl)

    def test_fan_in_is_last_level(self):
        """E is the only node with dependencies on B, C, D — it must be last."""
        _, levels = self._build(
            [_node("B"), _node("C"), _node("D"), _node("E")],
            [{"node": "E", "fan_in": [{"node": "B"}, {"node": "C"}, {"node": "D"}]}],
        )
        self.assertEqual(
            _level_of(levels, "E"),
            max(_level_of(levels, n) for n in ["B", "C", "D", "E"]),
        )


class TestEdgeSystemFanOutFanIn(unittest.TestCase):
    """Combined fan-out + fan-in: A→[B,C,D], E waits [B,C,D], E→F."""

    def setUp(self):
        c = _make_compiler(
            [_node("A"), _node("B"), _node("C"), _node("D"), _node("E"), _node("F")],
            [
                {"node": "A", "children": [{"node": "B"}, {"node": "C"}, {"node": "D"}]},
                {"node": "E",
                 "fan_in": [{"node": "B"}, {"node": "C"}, {"node": "D"}],
                 "children": [{"node": "F"}]},
            ],
        )
        self.deps = c._build_dag()
        self.levels = c._topological_levels(self.deps)

    def test_b_c_d_after_a(self):
        self.assertLess(_level_of(self.levels, "A"), _level_of(self.levels, "B"))

    def test_e_after_b_c_d(self):
        e_lvl = _level_of(self.levels, "E")
        self.assertLess(_level_of(self.levels, "B"), e_lvl)
        self.assertLess(_level_of(self.levels, "C"), e_lvl)
        self.assertLess(_level_of(self.levels, "D"), e_lvl)

    def test_f_after_e(self):
        self.assertLess(_level_of(self.levels, "E"), _level_of(self.levels, "F"))

    def test_b_c_d_no_direct_dep_on_each_other(self):
        """Siblings B, C, D must not depend on each other."""
        self.assertNotIn("C", self.deps["B"])
        self.assertNotIn("D", self.deps["B"])


class TestEdgeSystemValidation(unittest.TestCase):
    """Error and warning rules for the edge tree."""

    def test_unknown_node_raises_value_error(self):
        """A node referenced in edges but absent from nodes raises ValueError."""
        with self.assertRaises(ValueError):
            c = _make_compiler(
                [_node("A")],
                [{"node": "A", "children": [{"node": "GHOST"}]}],
            )
            c._build_dag()

    def test_cycle_raises_value_error(self):
        """A cycle within a single recursive declaration raises ValueError."""
        with self.assertRaises(ValueError):
            c = _make_compiler(
                [_node("A"), _node("B")],
                [{"node": "A", "children": [
                    {"node": "B", "children": [{"node": "A"}]}
                ]}],
            )
            c._build_dag()

    def test_depends_on_rejected_by_pydantic(self):
        """depends_on has been removed from GraphEdge — Pydantic must reject it."""
        with self.assertRaises((ValidationError, TypeError)):
            Graph.model_validate({
                "models": [{"llm": "ollama", "model": "dummy"}],
                "prompts": [{"template": {}}],
                "nodes": [_node("A")],
                "edges": [{"node": "A", "depends_on": ["B"]}],
            })

    def test_contradictory_structure_emits_warning(self):
        """Same node with different children in two declarations emits a warning."""
        c = _make_compiler(
            [_node("A"), _node("B"), _node("C"), _node("D"), _node("E")],
            [
                {"node": "A", "children": [
                    {"node": "B", "children": [{"node": "C"}]}
                ]},
                {"node": "E", "fan_in": [
                    {"node": "B", "children": [{"node": "D"}]}  # contradicts B→C above
                ]},
            ],
        )
        with self.assertLogs("kegal.compiler", level=logging.WARNING) as cm:
            c._build_dag()
        self.assertTrue(any("contradictory" in line for line in cm.output))


class TestEdgeSystemMessagePassingPreserved(unittest.TestCase):
    """Stage-2 inference must survive the refactoring unchanged."""

    def test_linear_pipeline_no_edges(self):
        """output→input inference works with edges: []."""
        c = _make_compiler(
            [_node("pre", mp_out=True), _node("ana", mp_in=True)],
            [],
        )
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        self.assertIn("pre", deps["ana"])
        self.assertLess(_level_of(levels, "pre"), _level_of(levels, "ana"))

    def test_guard_barrier_no_edges(self):
        """Guard node precedes all others even with no explicit edges."""
        c = _make_compiler(
            [_node("guard", guard=True), _node("worker")],
            [],
        )
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        self.assertIn("guard", deps["worker"])
        self.assertLess(_level_of(levels, "guard"), _level_of(levels, "worker"))


class TestCompilerClose(unittest.TestCase):
    """Compiler.close() lifecycle — no LLM required."""

    def _closeable(self):
        """Return a Compiler-like object with the attributes close() needs."""
        c = _make_compiler([_node("A")], [])
        c.mcp_handlers = {}
        c.clients = []
        return c

    def test_close_without_mcp_does_not_raise(self):
        """close() on a graph with no MCP servers must not raise."""
        c = self._closeable()
        c.close()

    def test_close_is_idempotent(self):
        """Calling close() twice must not raise."""
        c = self._closeable()
        c.close()
        c.close()

    def test_close_clears_mcp_handlers(self):
        """After close(), mcp_handlers must be empty."""
        c = self._closeable()
        # Simulate a connected handler with a no-op disconnect
        from unittest.mock import MagicMock
        fake_handler = MagicMock()
        c.mcp_handlers = {"srv": fake_handler}
        c.close()
        self.assertEqual(len(c.mcp_handlers), 0)
        fake_handler.disconnect.assert_called_once()

    def test_close_calls_disconnect_on_each_mcp_handler(self):
        """close() must call disconnect() on every active MCP handler."""
        from unittest.mock import MagicMock
        c = self._closeable()
        h1, h2 = MagicMock(), MagicMock()
        c.mcp_handlers = {"a": h1, "b": h2}
        c.close()
        h1.disconnect.assert_called_once()
        h2.disconnect.assert_called_once()

    def test_close_calls_client_close_when_available(self):
        """close() must call close() on LLM clients that expose it."""
        from unittest.mock import MagicMock
        c = self._closeable()
        mock_model = MagicMock(spec=["close"])  # has close()
        mock_client = MagicMock()
        mock_client.model = mock_model
        c.clients = [mock_client]
        c.close()
        mock_model.close.assert_called_once()

    def test_close_skips_client_without_close(self):
        """close() must not raise when an LLM client has no close() method."""
        from unittest.mock import MagicMock
        c = self._closeable()
        mock_model = MagicMock(spec=[])          # no close()
        mock_client = MagicMock()
        mock_client.model = mock_model
        c.clients = [mock_client]
        c.close()                                # must not raise


class TestFanOutGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "fanout_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_levels(self):
        """dispatcher must precede both analysts, which share the same level."""
        deps = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)

        dispatcher_lvl       = _level_of(levels, "dispatcher")
        economic_lvl         = _level_of(levels, "economic_analyst")
        environmental_lvl    = _level_of(levels, "environmental_analyst")

        self.assertLess(dispatcher_lvl, economic_lvl)
        self.assertLess(dispatcher_lvl, environmental_lvl)
        self.assertEqual(economic_lvl, environmental_lvl)

    def test_compile(self):
        """Fan-out graph must produce outputs for all three nodes."""
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("dispatcher", executed_ids)
        self.assertIn("economic_analyst", executed_ids)
        self.assertIn("environmental_analyst", executed_ids)


class TestFanInGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "fanin_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_levels(self):
        """Both analysts run at the same level; synthesizer comes after both."""
        deps = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)

        economic_lvl      = _level_of(levels, "economic_analyst")
        environmental_lvl = _level_of(levels, "environmental_analyst")
        synthesizer_lvl   = _level_of(levels, "synthesizer")

        self.assertEqual(economic_lvl, environmental_lvl)
        self.assertLess(economic_lvl, synthesizer_lvl)
        self.assertLess(environmental_lvl, synthesizer_lvl)

    def test_compile(self):
        """Fan-in graph must produce outputs for all three nodes."""
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("economic_analyst", executed_ids)
        self.assertIn("environmental_analyst", executed_ids)
        self.assertIn("synthesizer", executed_ids)


class TestFanOutFanInGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "fanout_fanin_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_levels(self):
        """dispatcher < analysts (parallel) < synthesizer — three distinct levels."""
        deps = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)

        dispatcher_lvl    = _level_of(levels, "dispatcher")
        economic_lvl      = _level_of(levels, "economic_analyst")
        environmental_lvl = _level_of(levels, "environmental_analyst")
        synthesizer_lvl   = _level_of(levels, "synthesizer")

        self.assertLess(dispatcher_lvl, economic_lvl)
        self.assertLess(dispatcher_lvl, environmental_lvl)
        self.assertEqual(economic_lvl, environmental_lvl)
        self.assertLess(economic_lvl, synthesizer_lvl)
        self.assertLess(environmental_lvl, synthesizer_lvl)

    def test_compile(self):
        """Combined fan-out + fan-in graph must produce outputs for all four nodes."""
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("dispatcher", executed_ids)
        self.assertIn("economic_analyst", executed_ids)
        self.assertIn("environmental_analyst", executed_ids)
        self.assertIn("synthesizer", executed_ids)


class TestRagGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "rag_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_init(self):
        pass  # Compiler created in setUp — just verify it constructs without error.

    def test_compile(self):
        self.compiler.compile()

    def test_compile_to_file(self):
        self.compiler.compile()
        out_dir = CURRENT_DIR / "graph_outputs" / "rag_graph"
        self.compiler.save_outputs_as_json(out_dir / "rag_graph.json")
        self.compiler.save_outputs_as_markdown(out_dir / "rag_graph.md")


class TestDagGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "dag_graph.yml"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_levels(self):
        """Verify correct DAG scheduling order."""
        deps = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)

        def level_of(nid):
            return next(i for i, lvl in enumerate(levels) if nid in lvl)

        guard_lvl      = level_of("guard_node")
        summarizer_lvl = level_of("summarizer")
        analyst_a_lvl  = level_of("analyst_a")
        analyst_b_lvl  = level_of("analyst_b")

        # guard_node has no deps → first level
        self.assertIn("guard_node", levels[0])

        # summarizer depends on guard (guard is guard-node barrier)
        self.assertGreater(summarizer_lvl, guard_lvl)

        # analyst_a depends on summarizer (message_passing output→input)
        self.assertGreater(analyst_a_lvl, summarizer_lvl)

        # analyst_b is isolated → only depends on guard, so comes before analyst_a
        self.assertGreater(analyst_b_lvl, guard_lvl)
        self.assertLessEqual(analyst_b_lvl, analyst_a_lvl)

    def test_dag_compile(self):
        """Full DAG compilation must produce outputs for all four nodes."""
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("guard_node", executed_ids)
        self.assertIn("summarizer", executed_ids)
        self.assertIn("analyst_a", executed_ids)
        self.assertIn("analyst_b", executed_ids)

    def test_dag_guard_blocks(self):
        """When guard returns validation=false the downstream nodes must NOT run."""
        self.compiler.user_message = "You are all idiots and I hate this stupid system!!!"
        self.compiler.compile()
        outputs = self.compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("guard_node", executed_ids)
        self.assertNotIn("summarizer", executed_ids)
        self.assertNotIn("analyst_a", executed_ids)
        self.assertNotIn("analyst_b", executed_ids)

    def test_dag_compile_to_file(self):
        self.compiler.compile()
        out_dir = CURRENT_DIR / "graph_outputs" / "dag_graph"
        self.compiler.save_outputs_as_json(out_dir / "dag_graph.json")
        self.compiler.save_outputs_as_markdown(out_dir / "dag_graph.md")


# ---------------------------------------------------------------------------
# _validate_prompts — placeholder pre-validation at init time
# ---------------------------------------------------------------------------

class TestValidatePrompts(unittest.TestCase):
    """_validate_prompts() warns about prompt placeholders that are referenced in
    a template but not activated in the corresponding node config."""

    def _make(self, node_cfg: dict, template: dict[str, str]) -> Compiler:
        """Build a minimal Compiler bypassing __init__, with only the fields
        _validate_prompts() needs: nodes, edges, and prompts."""
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
            "nodes": [node_cfg],
            "edges": [],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.prompts = [template]
        return c

    def _node_cfg(self, **overrides) -> dict:
        base: dict = {
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10,
            "show": False, "prompt": {"template": 0},
        }
        base.update(overrides)
        return base

    def test_unactivated_blackboard_warns(self):
        """{blackboard} in template but blackboard.read not enabled → warning."""
        c = self._make(
            self._node_cfg(),
            {"system": "", "user": "State of discussion:\n{blackboard}\nAnalyze."},
        )
        with self.assertLogs("kegal.compiler", level=logging.WARNING) as cm:
            c._validate_prompts()
        self.assertTrue(any("blackboard" in line for line in cm.output))

    def test_unactivated_user_message_warns(self):
        """{user_message} in template but user_message not enabled → warning."""
        c = self._make(
            self._node_cfg(),
            {"system": "", "user": "Respond to: {user_message}"},
        )
        with self.assertLogs("kegal.compiler", level=logging.WARNING) as cm:
            c._validate_prompts()
        self.assertTrue(any("user_message" in line for line in cm.output))

    def test_activated_user_message_no_warning(self):
        """{user_message} with user_message: true → no warning."""
        from unittest.mock import patch
        c = self._make(
            self._node_cfg(prompt={"template": 0, "user_message": True}),
            {"system": "", "user": "Respond to: {user_message}"},
        )
        with patch.object(logging.getLogger("kegal.compiler"), "warning") as mock_warn:
            c._validate_prompts()
        mock_warn.assert_not_called()

    def test_activated_blackboard_no_warning(self):
        """{blackboard} with blackboard.read=True → no warning."""
        from unittest.mock import patch
        c = self._make(
            self._node_cfg(blackboard={"read": True, "write": False}),
            {"system": "", "user": "State: {blackboard}\nAnalyze."},
        )
        with patch.object(logging.getLogger("kegal.compiler"), "warning") as mock_warn:
            c._validate_prompts()
        mock_warn.assert_not_called()

    def test_prompt_placeholders_covers_custom_key(self):
        """{custom_key} listed in prompt_placeholders → no warning."""
        from unittest.mock import patch
        c = self._make(
            self._node_cfg(prompt={"template": 0,
                                   "prompt_placeholders": {"custom_key": "value"}}),
            {"system": "", "user": "Focus on: {custom_key}"},
        )
        with patch.object(logging.getLogger("kegal.compiler"), "warning") as mock_warn:
            c._validate_prompts()
        mock_warn.assert_not_called()

    def test_template_with_no_placeholders_no_warning(self):
        """Template containing no {} tokens emits no warning."""
        from unittest.mock import patch
        c = self._make(
            self._node_cfg(),
            {"system": "You are a helpful assistant.",
             "user": "Answer the following question concisely."},
        )
        with patch.object(logging.getLogger("kegal.compiler"), "warning") as mock_warn:
            c._validate_prompts()
        mock_warn.assert_not_called()

    def test_system_template_placeholder_also_checked(self):
        """{user_message} in the system part of the template also triggers a warning."""
        c = self._make(
            self._node_cfg(),
            {"system": "You handle: {user_message}", "user": ""},
        )
        with self.assertLogs("kegal.compiler", level=logging.WARNING) as cm:
            c._validate_prompts()
        self.assertTrue(any("user_message" in line for line in cm.output))


# ---------------------------------------------------------------------------
# _run_parallel — exception propagation
# ---------------------------------------------------------------------------

class TestRunParallelFailure(unittest.TestCase):
    """_run_parallel raises RuntimeError after all futures drain when any node fails."""

    def test_failure_raises_runtime_error(self):
        """A node that raises during parallel execution → RuntimeError after pool drains."""
        from unittest.mock import patch

        c = _make_compiler([_node("A"), _node("B")], [])

        def fail_on_a(node):
            if node.id == "A":
                raise ValueError("intentional failure in A")

        with patch.object(c, "_run_node", side_effect=fail_on_a):
            with self.assertRaises(RuntimeError) as ctx:
                c._run_parallel(["A", "B"])
        self.assertIn("A", str(ctx.exception))

    def test_failure_is_chained_to_original_exception(self):
        """RuntimeError.__cause__ is the original exception from the failing node."""
        from unittest.mock import patch

        c = _make_compiler([_node("A"), _node("B")], [])
        original = ValueError("node A crashed")

        def always_fail(_node):
            raise original

        with patch.object(c, "_run_node", side_effect=always_fail):
            with self.assertRaises(RuntimeError) as ctx:
                c._run_parallel(["A", "B"])
        self.assertIs(ctx.exception.__cause__, original)

    def test_all_succeed_no_exception(self):
        """When all parallel nodes succeed _run_parallel returns without raising."""
        from unittest.mock import patch

        c = _make_compiler([_node("A"), _node("B")], [])
        with patch.object(c, "_run_node", return_value=None):
            c._run_parallel(["A", "B"])   # must not raise
