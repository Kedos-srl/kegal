"""Unit tests for batch inference Pydantic model fields (TDD — RED phase).

All tests are self-contained, no network, no LLM.
"""

import unittest
from pydantic import ValidationError

from kegal.graph import Graph
from kegal.graph_edge import GraphEdge
from kegal.graph_model import GraphModel
from kegal.graph_node import NodePrompt, GraphNode, NodeBatchMessagePassing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_graph(**overrides) -> dict:
    base = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": [
            {
                "id": "n",
                "model": 0,
                "temperature": 0.0,
                "max_tokens": 10,
                "show": False,
                "prompt": {"template": 0},
            }
        ],
        "edges": [{"node": "n"}],
    }
    base.update(overrides)
    return base


# ===========================================================================
# Graph — batch_user_messages
# ===========================================================================

class TestGraphBatchUserMessages(unittest.TestCase):

    def test_graph_accepts_batch_user_messages(self):
        """Graph must accept a batch_user_messages list of strings."""
        data = _base_graph(batch_user_messages=["msg 0", "msg 1", "msg 2"])
        g = Graph.model_validate(data)
        self.assertEqual(g.batch_user_messages, ["msg 0", "msg 1", "msg 2"])

    def test_graph_batch_user_messages_defaults_to_none(self):
        """batch_user_messages is optional and defaults to None."""
        g = Graph.model_validate(_base_graph())
        self.assertIsNone(g.batch_user_messages)

    def test_graph_rejects_both_user_message_and_batch_user_messages(self):
        """Setting both user_message and batch_user_messages must raise ValidationError."""
        data = _base_graph(
            user_message="single message",
            batch_user_messages=["msg 0", "msg 1"],
        )
        with self.assertRaises(ValidationError):
            Graph.model_validate(data)


# ===========================================================================
# NodePrompt — batch_use_messages
# ===========================================================================

class TestNodePromptBatchUseMessages(unittest.TestCase):

    def test_node_prompt_accepts_batch_use_messages(self):
        """NodePrompt must accept a batch_use_messages list of ints."""
        p = NodePrompt(template=0, batch_use_messages=[0, 1, 2])
        self.assertEqual(p.batch_use_messages, [0, 1, 2])

    def test_node_prompt_batch_use_messages_defaults_to_none(self):
        """batch_use_messages is optional and defaults to None."""
        p = NodePrompt(template=0)
        self.assertIsNone(p.batch_use_messages)

    def test_graph_node_prompt_with_batch_use_messages_validates(self):
        """A full graph with a node using batch_use_messages must validate."""
        data = _base_graph(
            batch_user_messages=["a", "b"],
            nodes=[{
                "id": "n",
                "model": 0,
                "temperature": 0.0,
                "max_tokens": 10,
                "show": False,
                "prompt": {"template": 0, "batch_use_messages": [0, 1]},
            }],
        )
        g = Graph.model_validate(data)
        self.assertEqual(g.nodes[0].prompt.batch_use_messages, [0, 1])


# ===========================================================================
# GraphNode — batch_message_passing
# ===========================================================================

class TestGraphNodeBatchMessagePassing(unittest.TestCase):

    def _make_node(self, **kwargs) -> dict:
        base = {
            "id": "n",
            "model": 0,
            "temperature": 0.0,
            "max_tokens": 10,
            "show": False,
            "prompt": {"template": 0},
        }
        base.update(kwargs)
        return base

    def test_node_accepts_batch_message_passing_output(self):
        """GraphNode must accept batch_message_passing with output=True."""
        data = _base_graph(nodes=[self._make_node(
            batch_message_passing={"output": True}
        )])
        g = Graph.model_validate(data)
        self.assertTrue(g.nodes[0].batch_message_passing.output)

    def test_node_accepts_batch_message_passing_input(self):
        """GraphNode must accept batch_message_passing with input=True."""
        data = _base_graph(nodes=[self._make_node(
            batch_message_passing={"input": True}
        )])
        g = Graph.model_validate(data)
        self.assertTrue(g.nodes[0].batch_message_passing.input)

    def test_node_batch_message_passing_defaults_to_none(self):
        """batch_message_passing is optional and defaults to None."""
        data = _base_graph()
        g = Graph.model_validate(data)
        self.assertIsNone(g.nodes[0].batch_message_passing)

    def test_node_batch_message_passing_class_importable(self):
        """NodeBatchMessagePassing must be importable from graph_node."""
        bmp = NodeBatchMessagePassing(input=True, output=False)
        self.assertTrue(bmp.input)
        self.assertFalse(bmp.output)


# ===========================================================================
# GraphEdge — batch_children / batch_fan_in
# ===========================================================================

class TestGraphEdgeBatchFields(unittest.TestCase):

    def test_edge_accepts_batch_children(self):
        """GraphEdge must accept batch_children as a list of sub-edges."""
        edge = GraphEdge.model_validate({
            "node": "parent",
            "batch_children": [{"node": "child_1"}, {"node": "child_2"}],
        })
        self.assertEqual(len(edge.batch_children), 2)
        self.assertEqual(edge.batch_children[0].node, "child_1")

    def test_edge_accepts_batch_fan_in(self):
        """GraphEdge must accept batch_fan_in as a list of sub-edges."""
        edge = GraphEdge.model_validate({
            "node": "synth",
            "batch_fan_in": [{"node": "branch_1"}, {"node": "branch_2"}],
        })
        self.assertEqual(len(edge.batch_fan_in), 2)

    def test_edge_batch_children_defaults_to_none(self):
        edge = GraphEdge(node="n")
        self.assertIsNone(edge.batch_children)

    def test_edge_batch_fan_in_defaults_to_none(self):
        edge = GraphEdge(node="n")
        self.assertIsNone(edge.batch_fan_in)

    def test_edge_rejects_batch_children_with_children(self):
        """batch_children and children must be mutually exclusive."""
        with self.assertRaises(ValidationError):
            GraphEdge.model_validate({
                "node": "n",
                "children": [{"node": "a"}],
                "batch_children": [{"node": "b"}],
            })

    def test_edge_rejects_batch_children_with_ordered_children(self):
        """batch_children and ordered_children must be mutually exclusive."""
        with self.assertRaises(ValidationError):
            GraphEdge.model_validate({
                "node": "n",
                "ordered_children": [{"node": "a"}],
                "batch_children": [{"node": "b"}],
            })

    def test_edge_rejects_batch_fan_in_with_fan_in(self):
        """batch_fan_in and fan_in must be mutually exclusive."""
        with self.assertRaises(ValidationError):
            GraphEdge.model_validate({
                "node": "n",
                "fan_in": [{"node": "a"}],
                "batch_fan_in": [{"node": "b"}],
            })

    def test_edge_rejects_batch_fan_in_with_ordered_fan_in(self):
        """batch_fan_in and ordered_fan_in must be mutually exclusive."""
        with self.assertRaises(ValidationError):
            GraphEdge.model_validate({
                "node": "n",
                "ordered_fan_in": [{"node": "a"}],
                "batch_fan_in": [{"node": "b"}],
            })


# ===========================================================================
# GraphModel — Bedrock batch fields
# ===========================================================================

class TestGraphModelBedrockBatchFields(unittest.TestCase):

    def test_graph_model_accepts_batch_role_arn(self):
        """GraphModel must accept batch_role_arn."""
        m = GraphModel(
            llm="bedrock",
            model="arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
            batch_role_arn="arn:aws:iam::123456789012:role/BatchRole",
        )
        self.assertEqual(m.batch_role_arn,
                         "arn:aws:iam::123456789012:role/BatchRole")

    def test_graph_model_accepts_s3_batch_uris(self):
        """GraphModel must accept batch_s3_input_uri and batch_s3_output_uri."""
        m = GraphModel(
            llm="bedrock",
            model="arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
            batch_s3_input_uri="s3://my-bucket/input",
            batch_s3_output_uri="s3://my-bucket/output",
        )
        self.assertEqual(m.batch_s3_input_uri, "s3://my-bucket/input")
        self.assertEqual(m.batch_s3_output_uri, "s3://my-bucket/output")

    def test_graph_model_batch_bedrock_fields_default_to_none(self):
        """Bedrock batch fields are all optional and default to None."""
        m = GraphModel(llm="anthropic", model="claude-3-5-sonnet-20241022")
        self.assertIsNone(m.batch_role_arn)
        self.assertIsNone(m.batch_s3_input_uri)
        self.assertIsNone(m.batch_s3_output_uri)


if __name__ == "__main__":
    unittest.main()
