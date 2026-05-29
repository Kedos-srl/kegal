import unittest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from kegal.compiler import Compiler, CompiledOutput
from kegal.graph import Graph
from kegal.graph_edge import GraphEdge


def _graph(nodes_cfg, edges_cfg):
    return Graph.model_validate({
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": nodes_cfg,
        "edges": edges_cfg,
    })


def _n(nid):
    return {"id": nid, "model": 0, "temperature": 0.0,
            "max_tokens": 100, "show": False, "prompt": {"template": 0}}


def _bare_compiler(nodes_cfg, edges_cfg):
    graph = _graph(nodes_cfg, edges_cfg)
    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    c.clients = [MagicMock()]
    c.context_windows = [None]
    c.prompts = []
    c.tools = None
    c.graph_mcp_servers = []
    c._board_entries = {}
    c.react_compact_prompts = []
    c._react_trace = {}
    c._react_controllers = c._build_react_controller_map()
    return c


def _runtime_compiler(nodes_cfg, edges_cfg):
    """Like _bare_compiler but also adds runtime state needed for _run_react_agent."""
    c = _bare_compiler(nodes_cfg, edges_cfg)
    c.message_passing = []
    c.outputs = CompiledOutput()
    c._boards = {}
    return c


class TestOrderedEdgesSchema(unittest.TestCase):

    def test_ordered_children_field_accepted(self):
        """ordered_children is a valid GraphEdge field."""
        g = _graph(
            [_n("parent"), _n("A"), _n("B")],
            [{"node": "parent", "ordered_children": [{"node": "A"}, {"node": "B"}]}],
        )
        edge = g.edges[0]
        self.assertIsNotNone(edge.ordered_children)
        self.assertEqual(len(edge.ordered_children), 2)

    def test_ordered_fan_in_field_accepted(self):
        """ordered_fan_in is a valid GraphEdge field."""
        g = _graph(
            [_n("A"), _n("B"), _n("synth")],
            [{"node": "synth", "ordered_fan_in": [{"node": "A"}, {"node": "B"}]}],
        )
        edge = g.edges[0]
        self.assertIsNotNone(edge.ordered_fan_in)
        self.assertEqual(len(edge.ordered_fan_in), 2)

    def test_react_and_ordered_children_mutually_exclusive(self):
        """react and ordered_children on the same edge must raise ValidationError."""
        with self.assertRaises(ValidationError):
            _graph(
                [_n("ctrl"), _n("agent")],
                [{"node": "ctrl",
                  "react": [{"node": "agent"}],
                  "ordered_children": [{"node": "agent"}]}],
            )

    def test_children_and_ordered_children_can_coexist(self):
        """children and ordered_children on the same edge are both valid."""
        g = _graph(
            [_n("p"), _n("A"), _n("B"), _n("C"), _n("D")],
            [{"node": "p",
              "children": [{"node": "A"}, {"node": "B"}],
              "ordered_children": [{"node": "C"}, {"node": "D"}]}],
        )
        self.assertIsNotNone(g.edges[0].children)
        self.assertIsNotNone(g.edges[0].ordered_children)


# ---------------------------------------------------------------------------
# Task 2 — Main DAG: ordered_children sequential deps
# ---------------------------------------------------------------------------

class TestOrderedChildrenDAG(unittest.TestCase):

    def test_ordered_children_sequential_deps(self):
        """A→B→C via ordered_children: B depends on A, C depends on B."""
        c = _bare_compiler(
            [_n("parent"), _n("A"), _n("B"), _n("C")],
            [{"node": "parent", "ordered_children": [
                {"node": "A"}, {"node": "B"}, {"node": "C"}
            ]}],
        )
        deps = c._build_dag()
        self.assertIn("parent", deps["A"])
        self.assertIn("A", deps["B"])
        self.assertIn("B", deps["C"])

    def test_ordered_children_single_item_only_depends_on_parent(self):
        """Single ordered_child still depends only on parent."""
        c = _bare_compiler(
            [_n("parent"), _n("A")],
            [{"node": "parent", "ordered_children": [{"node": "A"}]}],
        )
        deps = c._build_dag()
        self.assertIn("parent", deps["A"])

    def test_ordered_and_parallel_children_independent(self):
        """children (parallel) and ordered_children (sequential) on the same edge."""
        c = _bare_compiler(
            [_n("p"), _n("X"), _n("Y"), _n("A"), _n("B")],
            [{"node": "p",
              "children": [{"node": "X"}, {"node": "Y"}],
              "ordered_children": [{"node": "A"}, {"node": "B"}]}],
        )
        deps = c._build_dag()
        self.assertIn("p", deps["X"])
        self.assertNotIn("Y", deps["X"])
        self.assertIn("p", deps["Y"])
        self.assertNotIn("X", deps["Y"])
        self.assertIn("p", deps["A"])
        self.assertIn("A", deps["B"])

    def test_ordered_children_cycle_detected(self):
        """Cycle through ordered_children raises ValueError."""
        with self.assertRaises(ValueError):
            c = _bare_compiler(
                [_n("A"), _n("B")],
                [
                    {"node": "A", "ordered_children": [{"node": "B"}]},
                    {"node": "B", "ordered_children": [{"node": "A"}]},
                ],
            )
            c._build_dag()


# ---------------------------------------------------------------------------
# Task 3 — Main DAG: ordered_fan_in tests
# ---------------------------------------------------------------------------

class TestOrderedFanInDAG(unittest.TestCase):

    def test_ordered_fan_in_sequential_chain(self):
        """A→B→C→synth via ordered_fan_in."""
        c = _bare_compiler(
            [_n("A"), _n("B"), _n("C"), _n("synth")],
            [{"node": "synth", "ordered_fan_in": [
                {"node": "A"}, {"node": "B"}, {"node": "C"}
            ]}],
        )
        deps = c._build_dag()
        self.assertIn("A", deps["synth"])
        self.assertIn("B", deps["synth"])
        self.assertIn("C", deps["synth"])
        self.assertIn("A", deps["B"])
        self.assertIn("B", deps["C"])
        self.assertNotIn("B", deps["A"])

    def test_ordered_fan_in_single_item(self):
        """Single ordered_fan_in entry: synth depends on A, no chain."""
        c = _bare_compiler(
            [_n("A"), _n("synth")],
            [{"node": "synth", "ordered_fan_in": [{"node": "A"}]}],
        )
        deps = c._build_dag()
        self.assertIn("A", deps["synth"])

    def test_fan_in_and_ordered_fan_in_coexist(self):
        """fan_in (parallel) and ordered_fan_in (sequential) on the same edge."""
        c = _bare_compiler(
            [_n("X"), _n("Y"), _n("A"), _n("B"), _n("synth")],
            [{"node": "synth",
              "fan_in": [{"node": "X"}, {"node": "Y"}],
              "ordered_fan_in": [{"node": "A"}, {"node": "B"}]}],
        )
        deps = c._build_dag()
        self.assertIn("X", deps["synth"])
        self.assertIn("Y", deps["synth"])
        self.assertNotIn("Y", deps["X"])
        self.assertIn("A", deps["synth"])
        self.assertIn("B", deps["synth"])
        self.assertIn("A", deps["B"])


# ---------------------------------------------------------------------------
# Task 4 — React sub-graph: ordered_children and ordered_fan_in
# Tests exercise the real _run_react_agent call path via patched _run_node.
# ---------------------------------------------------------------------------

class TestOrderedEdgesReactSubgraph(unittest.TestCase):

    def _make_compiler_with_react(self, agent_edge):
        """Build a minimal runtime compiler whose react agent uses the given agent_edge."""
        # Collect all node ids from agent_edge recursively
        all_ids = set()

        def _collect_ids(e):
            all_ids.add(e.node)
            for x in (e.children or []):
                _collect_ids(x)
            for x in (e.fan_in or []):
                _collect_ids(x)
            for x in (e.ordered_children or []):
                _collect_ids(x)
            for x in (e.ordered_fan_in or []):
                _collect_ids(x)

        _collect_ids(agent_edge)

        ctrl_id = "ctrl"
        nodes_cfg = [
            {**_n(ctrl_id), "react": {"max_iterations": 1}},
        ] + [_n(nid) for nid in sorted(all_ids)]
        edges_cfg = [{"node": ctrl_id, "react": [agent_edge.model_dump(exclude_none=True)]}]
        c = _runtime_compiler(nodes_cfg, edges_cfg)
        return c, agent_edge

    def test_ordered_children_sequential_in_react_dispatch(self):
        """_run_react_agent executes ordered_children nodes in sequential order."""
        agent_edge = GraphEdge(
            node="agent",
            ordered_children=[GraphEdge(node="step_b"), GraphEdge(node="step_c")],
        )
        c, ae = self._make_compiler_with_react(agent_edge)

        call_order = []

        def fake_run_node(node):
            call_order.append(node.id)

        with patch.object(c, "_run_node", side_effect=fake_run_node):
            c._run_react_agent(ae, "input")

        # agent must run before step_b, and step_b before step_c
        self.assertIn("agent", call_order)
        self.assertIn("step_b", call_order)
        self.assertIn("step_c", call_order)
        self.assertLess(call_order.index("agent"), call_order.index("step_b"))
        self.assertLess(call_order.index("step_b"), call_order.index("step_c"))

    def test_ordered_fan_in_sequential_in_react_dispatch(self):
        """_run_react_agent executes ordered_fan_in nodes in sequential chain order."""
        agent_edge = GraphEdge(
            node="synth",
            ordered_fan_in=[GraphEdge(node="P"), GraphEdge(node="Q")],
        )
        c, ae = self._make_compiler_with_react(agent_edge)

        call_order = []

        def fake_run_node(node):
            call_order.append(node.id)

        with patch.object(c, "_run_node", side_effect=fake_run_node):
            c._run_react_agent(ae, "input")

        # P must run before Q (chain: P → Q → synth)
        self.assertIn("P", call_order)
        self.assertIn("Q", call_order)
        self.assertIn("synth", call_order)
        self.assertLess(call_order.index("P"), call_order.index("Q"))
        self.assertLess(call_order.index("Q"), call_order.index("synth"))


# ---------------------------------------------------------------------------
# Issue 1 — _collect_main_edge_ids must traverse ordered_children / ordered_fan_in
# ---------------------------------------------------------------------------

class TestCollectMainEdgeIds(unittest.TestCase):

    def test_ordered_children_node_in_main_edge_ids(self):
        """A node reachable only via ordered_children must appear in main_edge_ids."""
        c = _bare_compiler(
            [_n("parent"), _n("A"), _n("B")],
            [{"node": "parent", "ordered_children": [{"node": "A"}, {"node": "B"}]}],
        )
        main_ids = c._collect_main_edge_ids()
        self.assertIn("parent", main_ids)
        self.assertIn("A", main_ids)
        self.assertIn("B", main_ids)

    def test_ordered_fan_in_node_in_main_edge_ids(self):
        """A node reachable only via ordered_fan_in must appear in main_edge_ids."""
        c = _bare_compiler(
            [_n("A"), _n("B"), _n("synth")],
            [{"node": "synth", "ordered_fan_in": [{"node": "A"}, {"node": "B"}]}],
        )
        main_ids = c._collect_main_edge_ids()
        self.assertIn("synth", main_ids)
        self.assertIn("A", main_ids)
        self.assertIn("B", main_ids)


# ---------------------------------------------------------------------------
# Issue 2 — _collect_react_agent_ids must traverse ordered_children / ordered_fan_in
# ---------------------------------------------------------------------------

class TestCollectReactAgentIds(unittest.TestCase):

    def test_ordered_children_react_agent_ids_collected(self):
        """React agents nested under ordered_children must appear in react_agent_ids."""
        # ctrl node has ordered_children leading to an intermediate node that carries
        # the react list — we verify that a react subgraph under ordered_children is found.
        nodes_cfg = [
            {**_n("ctrl"), "react": {"max_iterations": 1}},
            _n("mid"),
            _n("agent"),
        ]
        # ctrl → ordered_children → [mid(react=[agent])]
        # mid itself is a controller under an ordered_children slot
        edges_cfg = [
            {
                "node": "ctrl",
                "ordered_children": [
                    {"node": "mid", "react": [{"node": "agent"}]}
                ],
            }
        ]
        c = _bare_compiler(nodes_cfg, edges_cfg)
        react_ids = c._collect_react_agent_ids()
        self.assertIn("agent", react_ids)

    def test_ordered_fan_in_react_agent_ids_collected(self):
        """React agents nested under ordered_fan_in must appear in react_agent_ids."""
        nodes_cfg = [
            {**_n("ctrl"), "react": {"max_iterations": 1}},
            _n("fi_node"),
            _n("agent"),
        ]
        edges_cfg = [
            {
                "node": "ctrl",
                "ordered_fan_in": [
                    {"node": "fi_node", "react": [{"node": "agent"}]}
                ],
            }
        ]
        c = _bare_compiler(nodes_cfg, edges_cfg)
        react_ids = c._collect_react_agent_ids()
        self.assertIn("agent", react_ids)


# ---------------------------------------------------------------------------
# Issues 4 & 5 — _check_react_edge_mixing must recurse into ordered_children
# ---------------------------------------------------------------------------

class TestCheckReactEdgeMixingOrderedChildren(unittest.TestCase):

    def test_check_react_edge_mixing_recurses_ordered_children(self):
        """react+fan_in conflict buried under ordered_children must be detected."""
        # Build a graph where the react+fan_in violation is inside an ordered_children slot.
        # The GraphEdge model validator does not catch this combination; the compiler
        # validation must find it during _check_react_edge_mixing traversal.
        nodes_cfg = [
            _n("root"),
            {**_n("mid"), "react": {"max_iterations": 1}},
            _n("agent"),
            _n("fi"),
        ]
        # root → ordered_children → [mid with react=[agent] AND fan_in=[fi]]
        # react + fan_in on the same edge is a validation error caught by compiler
        edges_cfg = [
            {
                "node": "root",
                "ordered_children": [
                    {
                        "node": "mid",
                        "react": [{"node": "agent"}],
                        "fan_in": [{"node": "fi"}],
                    }
                ],
            }
        ]
        graph = Graph.model_validate({
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
            "nodes": nodes_cfg,
            "edges": edges_cfg,
        })
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.clients = [MagicMock()]
        c.context_windows = [None]
        c.prompts = [{}]
        c.tools = None
        c.graph_mcp_servers = []
        c._board_entries = {}
        c.react_compact_prompts = []
        c._react_trace = {}
        c._react_controllers = {}
        c.mcp_handlers = {}
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("fan_in", str(ctx.exception))


# ---------------------------------------------------------------------------
# Task 5 — Validation: react XOR ordered_fan_in
# ---------------------------------------------------------------------------

class TestOrderedEdgesValidation(unittest.TestCase):

    def test_react_and_ordered_fan_in_raises(self):
        """react and ordered_fan_in on the same edge must raise ValueError at _validate_indices."""
        source = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
            "nodes": [
                {**_n("ctrl"), "react": {"max_iterations": 2}},
                _n("agent"),
                _n("X"),
            ],
            "edges": [{"node": "ctrl",
                       "react": [{"node": "agent"}],
                       "ordered_fan_in": [{"node": "X"}]}],
        }
        graph = Graph.model_validate(source)
        c = object.__new__(Compiler)
        c.nodes = {n.id: n for n in graph.nodes}
        c.edges = graph.edges
        c.clients = [MagicMock()]
        c.context_windows = [None]
        c.prompts = [{}]
        c.tools = None
        c.graph_mcp_servers = []
        c._board_entries = {}
        c.react_compact_prompts = []
        c._react_trace = {}
        c._react_controllers = {}
        c.mcp_handlers = {}
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("ordered_fan_in", str(ctx.exception))


class TestCollectOrderedMainIds(unittest.TestCase):

    def test_ordered_children_node_included(self):
        """Nodes reachable only via ordered_children appear in _collect_ordered_main_ids."""
        c = _bare_compiler(
            [_n("parent"), _n("A"), _n("B")],
            [{"node": "parent", "ordered_children": [{"node": "A"}, {"node": "B"}]}],
        )
        ids = c._collect_ordered_main_ids()
        self.assertIn("A", ids)
        self.assertIn("B", ids)

    def test_ordered_fan_in_node_included(self):
        """Nodes reachable only via ordered_fan_in appear in _collect_ordered_main_ids."""
        c = _bare_compiler(
            [_n("P"), _n("Q"), _n("synth")],
            [{"node": "synth", "ordered_fan_in": [{"node": "P"}, {"node": "Q"}]}],
        )
        ids = c._collect_ordered_main_ids()
        self.assertIn("P", ids)
        self.assertIn("Q", ids)
        self.assertIn("synth", ids)
