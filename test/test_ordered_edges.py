import unittest
from pydantic import ValidationError
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
