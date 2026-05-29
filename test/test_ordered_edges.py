import unittest
from unittest.mock import MagicMock
from pydantic import ValidationError
from kegal.compiler import Compiler
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
# ---------------------------------------------------------------------------

class TestOrderedEdgesReactSubgraph(unittest.TestCase):

    def test_ordered_children_sequential_in_react_dispatch(self):
        """ordered_children within a react dispatch creates sequential local_deps."""
        agent_edge = GraphEdge(
            node="agent",
            ordered_children=[GraphEdge(node="step_b"), GraphEdge(node="step_c")]
        )
        local_deps: dict = {}

        def collect(edge):
            nid = edge.node
            if nid not in local_deps:
                local_deps[nid] = set()
            for child in (edge.children or []):
                collect(child)
                local_deps[child.node].add(nid)
            for fi in (edge.fan_in or []):
                collect(fi)
                local_deps[nid].add(fi.node)
            prev = nid
            for child in (edge.ordered_children or []):
                collect(child)
                local_deps[child.node].add(prev)
                prev = child.node
            prev = None
            for fi in (edge.ordered_fan_in or []):
                collect(fi)
                local_deps[nid].add(fi.node)
                if prev is not None:
                    local_deps[fi.node].add(prev)
                prev = fi.node

        collect(agent_edge)
        self.assertIn("agent", local_deps["step_b"])
        self.assertIn("step_b", local_deps["step_c"])

    def test_ordered_fan_in_sequential_in_react_dispatch(self):
        """ordered_fan_in within a react dispatch creates sequential chain."""
        synth_edge = GraphEdge(
            node="synth",
            ordered_fan_in=[GraphEdge(node="P"), GraphEdge(node="Q")]
        )
        local_deps: dict = {}

        def collect(edge):
            nid = edge.node
            if nid not in local_deps:
                local_deps[nid] = set()
            for child in (edge.children or []):
                collect(child)
                local_deps[child.node].add(nid)
            for fi in (edge.fan_in or []):
                collect(fi)
                local_deps[nid].add(fi.node)
            prev = nid
            for child in (edge.ordered_children or []):
                collect(child)
                local_deps[child.node].add(prev)
                prev = child.node
            prev = None
            for fi in (edge.ordered_fan_in or []):
                collect(fi)
                local_deps[nid].add(fi.node)
                if prev is not None:
                    local_deps[fi.node].add(prev)
                prev = fi.node

        collect(synth_edge)
        self.assertIn("P", local_deps["synth"])
        self.assertIn("Q", local_deps["synth"])
        self.assertIn("P", local_deps["Q"])


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
